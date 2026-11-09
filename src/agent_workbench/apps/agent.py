"""LangGraph agent: the graph and the process-wide runtime (chat model, saver, graph)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent_workbench.adapters.config import load_llm_config
from agent_workbench.adapters.llm import create_chat_model
from agent_workbench.core.config import LLMConfig

AGENT_MAX_STEPS = 50  # mcp_coder AGENT_MAX_STEPS
MODEL_TIMEOUT = 300  # HTTP timeout of the chat model (ICODER_LLM_TIMEOUT_SECONDS)


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
