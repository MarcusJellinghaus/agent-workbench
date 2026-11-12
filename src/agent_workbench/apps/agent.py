"""LangGraph agent: the graph, the process-wide runtime and one chat turn."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError, NodeCancelledError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent_workbench.adapters import config, llm
from agent_workbench.adapters.config import load_llm_config
from agent_workbench.adapters.llm import create_chat_model
from agent_workbench.adapters.llm_types import UsageInfo
from agent_workbench.adapters.tools import Toolsets, build_toolsets, to_structured_tool
from agent_workbench.adapters.toolset_providers import provider_packages
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.types import TokenUsage
from agent_workbench.services.logging_setup import clamp_loggers
from agent_workbench.services.tool_call_log import wrap_spec
from agent_workbench.services.tool_filter import enabled_specs

logger = logging.getLogger(__name__)

AGENT_MAX_STEPS = 50  # mcp_coder AGENT_MAX_STEPS
MODEL_TIMEOUT = 300  # HTTP timeout of the chat model (ICODER_LLM_TIMEOUT_SECONDS)
IDLE_TIMEOUT = (
    300  # ICODER_LLM_TIMEOUT_SECONDS: no stream event for this long fails the turn
)
OVERALL_TIMEOUT = 3600  # mcp_coder _AGENT_OVERALL_TIMEOUT

ToolStart = Callable[[str, str, dict[str, Any]], Awaitable[None]]  # run_id, name, args
ToolEnd = Callable[[str, str], Awaitable[None]]  # run_id, output text

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
    # The default handler re-raises everything except ToolInvocationError; with True
    # every tool exception becomes an error ToolMessage (its text goes to the provider)
    # and the turn continues. asyncio.CancelledError is not an Exception and propagates.
    graph.add_node("tools", ToolNode(list(tools), handle_tool_errors=True))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=checkpointer)


def sessions_dir() -> Path:
    """Return ``<app-data>/sessions``, the folder of the session databases (created)."""
    path = config.app_data_dir() / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def open_checkpointer(path: Path) -> AsyncSqliteSaver:
    """Open the SQLite checkpointer on *path* with ``secure_delete`` and its tables.

    Must be called on the event loop that uses the saver: it captures the running loop.

    Args:
        path: The database file, created if missing.

    Returns:
        The set-up saver; close it with ``await saver.conn.close()``.
    """
    conn = await aiosqlite.connect(path)
    try:
        # Per connection: deleted rows are overwritten with zeros.
        async with conn.execute("PRAGMA secure_delete=ON"):
            pass
        saver = AsyncSqliteSaver(conn)
        # Creates the tables (else adelete_thread fails on a fresh file) and sets WAL.
        await saver.setup()
    except BaseException:
        await conn.close()
        raise
    return saver


async def checkpoint_wal(saver: AsyncSqliteSaver) -> None:
    """Move the WAL into the database file and empty it; log, never raise, on failure.

    Call only after ``adelete_thread`` has returned: this takes ``saver.lock``, which
    is not reentrant.

    Args:
        saver: The checkpointer from :func:`open_checkpointer`.
    """
    try:
        # Under the saver's lock: its writes run execute + commit under it, so the
        # pragma cannot land inside one of them.
        async with (
            saver.lock,
            saver.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)") as cursor,
        ):
            row = await cursor.fetchone()
        if row and row[0]:
            logger.warning("WAL checkpoint of the checkpointer database was busy")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("WAL checkpoint of the checkpointer database failed")


@dataclass(frozen=True)
class Runtime:
    """The process-wide agent objects.

    ``toolsets`` is None without a ``[tools]`` table; kept for #19's Reload.
    """

    graph: Any
    chat_model: Any
    llm_config: LLMConfig
    checkpointer: Any
    toolsets: Toolsets | None = None


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


def build_tools(toolsets: Toolsets) -> list[StructuredTool]:
    """Return the enabled specs, logged and adapted, as LangChain tools.

    Filtered before adapting, so tools that are not enabled are never bound.

    Args:
        toolsets: The built toolsets of the configured providers.

    Returns:
        One tool per enabled spec, in spec order.
    """
    return [to_structured_tool(wrap_spec(s)) for s in enabled_specs(toolsets.specs)]


async def _open_runtime() -> Runtime:
    """Build the runtime; close what was opened if a later step fails.

    Returns:
        The new runtime.
    """
    config_file = config.read_config_file()
    llm_config = load_llm_config(config_file)
    chat_model = create_chat_model(llm_config, MODEL_TIMEOUT)
    toolsets: Toolsets | None = None
    saver: AsyncSqliteSaver | None = None
    try:
        # A non-table [tools] reaches build_toolsets and raises: no silent run
        # without tools.
        if config_file.tools or config_file.tools_type_error:
            # Registered names only; unknown names fail in the build.
            clamp_loggers(provider_packages(config_file.tools))
            toolsets = build_toolsets(config_file)
        saver = await open_checkpointer(sessions_dir() / "checkpoints.sqlite")
        tools = build_tools(toolsets) if toolsets is not None else []
        graph = build_graph(chat_model, tools, saver)
    except BaseException:
        try:
            if saver is not None:
                await saver.conn.close()
        finally:
            if toolsets is not None:
                toolsets.close()
        raise
    return Runtime(
        graph=graph,
        chat_model=chat_model,
        llm_config=llm_config,
        checkpointer=saver,
        toolsets=toolsets,
    )


async def get_runtime() -> Runtime:
    """Process-wide runtime, created on first call.

    Returns:
        The runtime shared by all chats. An invalid ``[tools]`` config or a
        toolset that cannot be built raises ``ValueError``.
    """
    global _runtime  # pylint: disable=global-statement
    # Opening the checkpointer awaits: without the lock, concurrent first calls
    # would each build a runtime.
    async with _runtime_lock:
        if _runtime is None:
            _runtime = await _open_runtime()
    return _runtime


async def close_runtime() -> None:
    """Close the checkpointer's connection and the toolsets; drop the runtime.

    No-op without a runtime. The toolsets are closed even if closing the
    connection raises.
    """
    global _runtime  # pylint: disable=global-statement
    async with _runtime_lock:
        if _runtime is None:
            return
        runtime, _runtime = _runtime, None
        try:
            await runtime.checkpointer.conn.close()
        finally:
            if runtime.toolsets is not None:
                runtime.toolsets.close()


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
    on_tool_start: ToolStart | None = None,
    on_tool_end: ToolEnd | None = None,
) -> str | None:
    """Run one turn; stream text via *on_text*; return an error message or None.

    Stop (cancelling the calling task) propagates as ``asyncio.CancelledError``
    and adds no message.

    The inactivity limit applies per model call: it is paused from a tool start to
    the next model start, so a long tool run does not fail the turn. The overall
    limit always applies.

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
        idle_timeout: Seconds without a stream event before the turn fails
            (paused while tools run).
        overall_timeout: Seconds the whole turn may take.
        on_tool_start: Receives ``(run_id, tool name, args)`` when a tool starts.
        on_tool_end: Receives ``(run_id, output text)`` when a tool ends or fails.

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
    paused = False
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
                kind = event["event"]
                if kind == "on_tool_start":
                    paused = True
                elif kind == "on_chat_model_start":
                    paused = False
                idle.reschedule(None if paused else loop.time() + idle_timeout)
                if kind == "on_chat_model_stream":
                    delta = event["data"]["chunk"].text
                    if delta:
                        await on_text(delta)
                        streamed = True
                elif kind == "on_chat_model_end":
                    usage = llm.add_usage(usage, event["data"]["output"])
                else:
                    await _tool_event(event, on_tool_start, on_tool_end)
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


async def _tool_event(
    event: Any, on_tool_start: ToolStart | None, on_tool_end: ToolEnd | None
) -> None:
    """Pass a tool start / end / error stream event to its callback; ignore others."""
    kind = event["event"]
    data = event["data"]
    if kind == "on_tool_start" and on_tool_start is not None:
        await on_tool_start(event["run_id"], event["name"], data.get("input") or {})
    elif kind == "on_tool_end" and on_tool_end is not None:
        output = data.get("output")
        await on_tool_end(event["run_id"], str(getattr(output, "content", output)))
    # A raising tool emits on_tool_error, not on_tool_end, even with
    # handle_tool_errors=True: the ToolNode builds the error ToolMessage afterwards.
    elif kind == "on_tool_error" and on_tool_end is not None:
        await on_tool_end(event["run_id"], str(data.get("error")))


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
