"""LangGraph agent: the graph, the process-wide runtime and one chat turn."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError, NodeCancelledError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from agent_workbench.adapters import config, llm
from agent_workbench.adapters.config import ConfigFile, load_llm_config
from agent_workbench.adapters.llm import create_chat_model
from agent_workbench.adapters.llm_types import UsageInfo
from agent_workbench.adapters.tools import to_structured_tool
from agent_workbench.adapters.toolset_providers import Toolsets
from agent_workbench.apps.permission_gate import (
    TURN_PERMISSIONS_KEY,
    Confirm,
    TurnPermissions,
    make_tool_node,
)
from agent_workbench.apps.tool_setup import build_configured_toolsets
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.permissions import PermissionMode
from agent_workbench.core.types import TokenUsage
from agent_workbench.services.permissions import PermissionConfig, parse_permissions
from agent_workbench.services.tool_call_log import wrap_spec

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import ToolSpec

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


def build_graph(
    chat_model: Any,
    tools: Sequence[Any],
    checkpointer: Any,
    *,
    modes: Mapping[str, PermissionMode],
) -> Any:
    """Compile model node → gated ToolNode, routed by tools_condition.

    A bound tool missing from *modes* or mapped to ``deny`` raises ``ValueError``.

    Args:
        chat_model: A ``BaseChatModel``; tools are bound only when there are any.
        tools: The tools offered to the model.
        checkpointer: The LangGraph checkpoint saver keeping the threads.
        modes: ``{tool name: mode}`` for every configured tool, ``deny`` included.

    Returns:
        The compiled graph.
    """
    tool_node = make_tool_node(tools, modes)
    model = chat_model.bind_tools(tools) if tools else chat_model

    async def call_model(state: MessagesState) -> dict[str, Any]:
        return {"messages": [await model.ainvoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", tool_node)
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

    ``toolsets`` and ``permissions`` are None without a ``[tools]`` table; both are
    kept for #19's Reload.
    """

    graph: Any
    chat_model: Any
    llm_config: LLMConfig
    checkpointer: Any
    toolsets: Toolsets | None = None
    permissions: PermissionConfig | None = None


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


def tool_modes(
    permissions: PermissionConfig, specs: Iterable["ToolSpec"]
) -> dict[str, PermissionMode]:
    """Return ``{spec name: effective mode}`` for every spec, ``deny`` included.

    Args:
        permissions: The parsed ``[permissions]`` config.
        specs: The specs of all configured toolsets.

    Returns:
        The mode of each spec, in spec order.
    """
    return {s.name: permissions.mode_of(s.name, s.group)[0] for s in specs}


def build_tools(
    toolsets: Toolsets, modes: Mapping[str, PermissionMode]
) -> list[StructuredTool]:
    """Return the specs whose mode is not ``deny``, logged and adapted, as LangChain tools.

    Filtered before adapting, so ``deny`` tools are never bound.

    Args:
        toolsets: The built toolsets of the configured providers.
        modes: ``{tool name: mode}`` for every spec of *toolsets*.

    Returns:
        One tool per spec that is not ``deny``, in spec order.
    """
    return [
        to_structured_tool(wrap_spec(s))
        for s in toolsets.specs
        if modes[s.name] != "deny"
    ]


def _runtime_permissions(
    config_file: ConfigFile, toolsets: Toolsets
) -> PermissionConfig:
    """Parse ``[permissions]`` against the configured specs.

    Warnings never raise; they are shown by ``verify``.

    Args:
        config_file: The read config file.
        toolsets: The built toolsets of the configured providers.

    Returns:
        The valid entries.

    Raises:
        ValueError: If ``[permissions]`` has error rows.
    """
    permissions, rows = parse_permissions(
        config_file.permissions,
        config_file.permissions_type_error,
        {s.name: s.group for s in toolsets.specs},
    )
    errors = [f"{label} {msg}" for label, status, msg in rows if status == "error"]
    if errors:
        raise ValueError("Invalid [permissions] config: " + "; ".join(errors))
    return permissions


async def _open_runtime() -> Runtime:
    """Build the runtime; close what was opened if a later step fails.

    Returns:
        The new runtime.
    """
    config_file = config.read_config_file()
    llm_config = load_llm_config(config_file)
    chat_model = create_chat_model(llm_config, MODEL_TIMEOUT)
    toolsets: Toolsets | None = None
    permissions: PermissionConfig | None = None
    modes: dict[str, PermissionMode] = {}
    tools: list[StructuredTool] = []
    saver: AsyncSqliteSaver | None = None
    try:
        toolsets = build_configured_toolsets(config_file)
        saver = await open_checkpointer(sessions_dir() / "checkpoints.sqlite")
        # Without [tools], [permissions] is not checked.
        if toolsets is not None:
            permissions = _runtime_permissions(config_file, toolsets)
            modes = tool_modes(permissions, toolsets.specs)
            tools = build_tools(toolsets, modes)
        graph = build_graph(chat_model, tools, saver, modes=modes)
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
        permissions=permissions,
    )


async def get_runtime() -> Runtime:
    """Process-wide runtime, created on first call.

    Returns:
        The runtime shared by all chats. An invalid ``[tools]`` config, a
        toolset that cannot be built or, with ``[tools]``, an invalid
        ``[permissions]`` config raises ``ValueError``.
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


class _IdleTimer:
    """Drives the turn's inactivity timer: paused while a tool runs or a dialog is open."""

    def __init__(self, idle: asyncio.Timeout, idle_timeout: float) -> None:
        self._idle = idle
        self._idle_timeout = idle_timeout
        self._tool_paused = False
        self._dialogs_open = 0

    def _rearm(self) -> None:
        """Pause or restart the timer; never touch an expired one (its error wins)."""
        if self._idle.expired():
            return
        if self._tool_paused or self._dialogs_open:
            self._idle.reschedule(None)
        else:
            when = asyncio.get_running_loop().time() + self._idle_timeout
            self._idle.reschedule(when)

    def on_event(self, kind: str) -> None:
        """Restart the timer for a stream event of *kind*; a tool start pauses it."""
        if kind == "on_tool_start":
            self._tool_paused = True
        elif kind == "on_chat_model_start":
            self._tool_paused = False
        self._rearm()

    def paused_during(self, confirm: Confirm) -> Confirm:
        """Return *confirm* wrapped so the timer is paused while its dialog is open.

        The end of a dialog does not restart the timer while a tool still runs.
        """

        async def paused_confirm(
            name: str, args: dict[str, Any], mode: PermissionMode
        ) -> bool:
            self._dialogs_open += 1
            self._rearm()
            try:
                return await confirm(name, args, mode)
            finally:
                self._dialogs_open -= 1
                self._rearm()

        return paused_confirm


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
    confirm: Confirm | None = None,
    grants: set[str] | None = None,
) -> str | None:
    """Run one turn; stream text via *on_text*; return an error message or None.

    Stop (cancelling the calling task) propagates as ``asyncio.CancelledError``
    and adds no message.

    The inactivity limit applies per model call: it is paused from a tool start to
    the next model start, and while an approval dialog is open, so a long tool run
    or a slow answer to a dialog does not fail the turn. The overall limit always
    applies.

    *confirm* and *grants* reach the permission gate as one ``TurnPermissions`` under
    ``configurable[TURN_PERMISSIONS_KEY]``; they are not checkpointed.

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
            (paused while tools run or a dialog is open).
        overall_timeout: Seconds the whole turn may take.
        on_tool_start: Receives ``(run_id, tool name, args)`` when a tool starts.
        on_tool_end: Receives ``(run_id, output text)`` when a tool ends or fails.
        confirm: Asks the user to approve an ``ask`` / ``ask_session`` call. None:
            every such call is refused.
        grants: The conversation's ``ask_session`` grants (tool names), filled by
            the gate; a new empty set when None. Used only with *confirm*.

    Returns:
        ``None`` on success, else the user-facing error message.

    Raises:
        asyncio.CancelledError: The turn was stopped.
    """
    overall = asyncio.timeout(overall_timeout)
    idle = asyncio.timeout(idle_timeout)
    timer = _IdleTimer(idle, idle_timeout)
    configurable: dict[str, Any] = {"thread_id": thread_id}
    if confirm is not None:
        configurable[TURN_PERMISSIONS_KEY] = TurnPermissions(
            confirm=timer.paused_during(confirm),
            grants=grants if grants is not None else set(),
            lock=asyncio.Lock(),
        )
    run_config = {"configurable": configurable, "recursion_limit": AGENT_MAX_STEPS}
    graph_input = {"messages": [HumanMessage(content=text)]}
    usage: UsageInfo = {}
    streamed = False
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
                timer.on_event(kind)
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
