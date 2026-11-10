"""LangGraph agent: the graph, the process-wide runtime and one chat turn."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError, NodeCancelledError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent_workbench.adapters import llm
from agent_workbench.adapters.config import load_llm_config
from agent_workbench.adapters.llm import create_chat_model
from agent_workbench.adapters.llm_types import UsageInfo
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.types import TokenUsage

AGENT_MAX_STEPS = 50  # mcp_coder AGENT_MAX_STEPS
MODEL_TIMEOUT = 300  # HTTP timeout of the chat model (ICODER_LLM_TIMEOUT_SECONDS)
IDLE_TIMEOUT = (
    300  # ICODER_LLM_TIMEOUT_SECONDS: no stream event for this long fails the turn
)
OVERALL_TIMEOUT = 3600  # mcp_coder _AGENT_OVERALL_TIMEOUT

_IDLE_MSG = "No response from the model for {s} s – turn aborted."
_OVERALL_MSG = "Turn exceeded {s} s – aborted."
_STEPS_MSG = (
    "Step limit of {n} reached – turn aborted. You can continue the conversation."
)


def build_graph(chat_model: Any, tools: Sequence[Any], checkpointer: Any) -> Any:
    """Compile model node → ToolNode, routed by tools_condition.

    Args:
        chat_model: A ``BaseChatModel``; tools are bound only when there are any.
        tools: The tools offered to the model.
        checkpointer: The LangGraph checkpoint saver keeping the threads.

    Returns:
        The compiled graph.
    """
    model = chat_model.bind_tools(tools) if tools else chat_model

    async def call_model(state: MessagesState) -> dict[str, Any]:
        return {"messages": [await model.ainvoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(list(tools)))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=checkpointer)


@dataclass(frozen=True)
class Runtime:
    """The process-wide agent objects."""

    graph: Any
    chat_model: Any
    llm_config: LLMConfig


_runtime: Runtime | None = None


async def get_runtime() -> Runtime:
    """Process-wide runtime, created on first call (#16 swaps the saver here).

    Returns:
        The runtime shared by all chats.
    """
    global _runtime  # pylint: disable=global-statement
    # No lock: nothing below awaits, so concurrent first calls cannot interleave.
    # #16 adds an asyncio.Lock together with the async SQLite saver.
    if _runtime is None:
        llm_config = load_llm_config()
        chat_model = create_chat_model(llm_config, MODEL_TIMEOUT)
        graph = build_graph(chat_model, [], InMemorySaver())
        _runtime = Runtime(graph=graph, chat_model=chat_model, llm_config=llm_config)
    return _runtime


def _last_ai_text(messages: Sequence[Any]) -> str:
    """Return the text of the last ``AIMessage`` in *messages* ("" if there is none)."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.text)
    return ""


async def run_turn(  # pylint: disable=too-many-arguments
    graph: Any,
    chat_model: Any,
    llm_config: LLMConfig,
    text: str,
    thread_id: str,
    on_text: Callable[[str], Awaitable[None]],
    token_usage: TokenUsage,
    *,
    idle_timeout: float = IDLE_TIMEOUT,
    overall_timeout: float = OVERALL_TIMEOUT,
) -> str | None:
    """Run one turn; stream text via *on_text*; return an error message or None.

    Stop (cancelling the calling task) propagates as ``asyncio.CancelledError``
    and adds no message.

    Args:
        graph: The compiled graph from :func:`build_graph`.
        chat_model: The chat model inside *graph* (for error mapping).
        llm_config: The LLM configuration *chat_model* was built from.
        text: The user's message.
        thread_id: The checkpointer thread holding the conversation.
        on_text: Receives each streamed text delta, or the final answer at once
            when the model did not stream.
        token_usage: Updated with the turn's summed usage, only when the turn
            completed.
        idle_timeout: Seconds without a stream event before the turn fails.
        overall_timeout: Seconds the whole turn may take.

    Returns:
        ``None`` on success, else the user-facing error message.

    Raises:
        asyncio.CancelledError: The turn was stopped.
    """
    run_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": AGENT_MAX_STEPS,
    }
    graph_input = {"messages": [HumanMessage(content=text)]}
    loop = asyncio.get_running_loop()
    usage: UsageInfo = {}
    streamed = False
    overall = asyncio.timeout(overall_timeout)
    idle = asyncio.timeout(idle_timeout)
    try:
        async with (
            overall,
            idle,
            aclosing(
                graph.astream_events(graph_input, run_config, version="v2")
            ) as events,
        ):
            async for event in events:
                idle.reschedule(loop.time() + idle_timeout)
                if event["event"] == "on_chat_model_stream":
                    delta = event["data"]["chunk"].text
                    if delta:
                        await on_text(delta)
                        streamed = True
                elif event["event"] == "on_chat_model_end":
                    usage = llm.add_usage(usage, event["data"]["output"])
        if not streamed:
            state = await graph.aget_state(run_config)
            final_text = _last_ai_text(state.values.get("messages", []))
            if final_text:
                await on_text(final_text)
        token_usage.update(
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("cache_read_input_tokens", 0),
        )
        return None
    except TimeoutError as exc:
        if overall.expired():
            return _OVERALL_MSG.format(s=overall_timeout)
        if idle.expired():
            return _IDLE_MSG.format(s=idle_timeout)
        # Raised by the provider, not by a turn timer.
        return await _provider_error_message(exc, llm_config, chat_model)
    except GraphRecursionError:
        return _STEPS_MSG.format(n=AGENT_MAX_STEPS)
    except NodeCancelledError as exc:
        # A timer cancelling the stalled node can surface as langgraph's wrapper.
        if overall.expired():
            return _OVERALL_MSG.format(s=overall_timeout)
        if idle.expired():
            return _IDLE_MSG.format(s=idle_timeout)
        raise asyncio.CancelledError() from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return await _provider_error_message(exc, llm_config, chat_model)


async def _provider_error_message(
    exc: Exception, llm_config: LLMConfig, chat_model: Any
) -> str:
    """Return the user-facing message of *exc* mapped by ``map_provider_error``.

    Runs in a thread: on a 404 the mapping lists models over the network.

    Raises:
        AssertionError: If map_provider_error returns instead of raising
            (should not happen).
    """
    try:
        await asyncio.to_thread(llm.map_provider_error, exc, llm_config, chat_model)
    except Exception as mapped:  # pylint: disable=broad-exception-caught
        return f"Error: {mapped}"
    raise AssertionError("map_provider_error always raises")  # pragma: no cover
