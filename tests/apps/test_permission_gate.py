"""Permission gate: outcomes, denial messages, ``ask_session`` grants, dialog lock, graph."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolRuntime
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from mcp_coder_utils.tool_spec import tool_spec

from agent_workbench.adapters.tools import to_structured_tool
from agent_workbench.apps import agent
from agent_workbench.apps.permission_gate import (
    DENY_UNAVAILABLE,
    DENY_USER,
    TURN_PERMISSIONS_KEY,
    TurnPermissions,
    gate_tool_call,
    make_tool_node,
)
from agent_workbench.core.permissions import PermissionMode
from tests.langchain_doubles import make_scripted_chat_model

RAN = "ran"


def _tool(name: str, ran: list[str] | None = None) -> StructuredTool:
    """Return a real tool *name* with a required ``text``; records each run in *ran*."""

    def run(text: str) -> str:
        """Record the run and echo *text*."""
        if ran is not None:
            ran.append(name)
        return f"{name}: {text}"

    spec = tool_spec(run, group="fake.read", read_only=True, name=name)
    return to_structured_tool(spec)


class Dialog:
    """Confirm callback answering *answers* in order (then the last); records calls."""

    def __init__(self, *answers: bool, delay: float = 0.0) -> None:
        self.answers = list(answers) or [True]
        self.delay = delay
        self.calls: list[tuple[str, dict[str, Any], PermissionMode]] = []
        self.events: list[str] = []
        self.entered = asyncio.Event()

    async def __call__(
        self, name: str, args: dict[str, Any], mode: PermissionMode
    ) -> bool:
        self.calls.append((name, args, mode))
        self.events.append(f"enter {name}")
        self.entered.set()
        await asyncio.sleep(self.delay)
        self.events.append(f"exit {name}")
        index = min(len(self.calls), len(self.answers)) - 1
        return self.answers[index]


def _turn(confirm: Any, grants: set[str] | None = None) -> TurnPermissions:
    return TurnPermissions(
        confirm=confirm,
        grants=set() if grants is None else grants,
        lock=asyncio.Lock(),
    )


def _request(
    name: str,
    args: dict[str, Any],
    tool: StructuredTool | None,
    turn: TurnPermissions | None = None,
    call_id: str = "call-1",
) -> ToolCallRequest:
    configurable: dict[str, Any] = {"thread_id": "t1"}
    if turn is not None:
        configurable[TURN_PERMISSIONS_KEY] = turn
    runtime = ToolRuntime(
        state={},
        context=None,
        config={"configurable": configurable},
        stream_writer=lambda _chunk: None,
        tool_call_id=call_id,
        store=None,
    )
    call = {"name": name, "args": args, "id": call_id, "type": "tool_call"}
    return ToolCallRequest(tool_call=call, tool=tool, state={}, runtime=runtime)


class Execute:
    """Stub ``execute``: records the requests and answers ``ok``."""

    def __init__(self) -> None:
        self.requests: list[ToolCallRequest] = []

    async def __call__(self, request: ToolCallRequest) -> ToolMessage | Command:
        self.requests.append(request)
        call = request.tool_call
        return ToolMessage(content=RAN, name=call["name"], tool_call_id=call["id"])


def _log_lines(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "logs" / "tool_calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _outcomes(tmp_path: Path) -> list[str]:
    return [line["outcome"] for line in _log_lines(tmp_path)]


def _assert_denial(result: Any, text: str, call_id: str = "call-1") -> None:
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == call_id
    assert result.content == text


# --- outcomes of gate_tool_call ---------------------------------------------------


async def test_deny_tool_is_blocked(tmp_path: Path) -> None:
    execute = Execute()
    request = _request("secret", {"text": "x"}, None, _turn(Dialog()))

    result = await gate_tool_call(request, execute, modes={"secret": "deny"})

    assert execute.requests == [request]
    assert isinstance(result, ToolMessage) and result.content == RAN
    assert _outcomes(tmp_path) == ["blocked"]
    assert _log_lines(tmp_path)[0]["result_size"] is None


async def test_unknown_name_is_logged(tmp_path: Path) -> None:
    execute = Execute()
    request = _request("missing", {}, None, _turn(Dialog()))

    await gate_tool_call(request, execute, modes={})

    assert execute.requests == [request]
    assert _outcomes(tmp_path) == ["unknown_tool"]


async def test_invalid_arguments_are_logged_and_not_confirmed(tmp_path: Path) -> None:
    dialog = Dialog()
    execute = Execute()
    request = _request("echo", {}, _tool("echo"), _turn(dialog))

    await gate_tool_call(request, execute, modes={"echo": "ask"})

    assert execute.requests == [request]
    assert not dialog.calls
    assert _outcomes(tmp_path) == ["invalid_arguments"]


async def test_allow_runs_without_dialog(tmp_path: Path) -> None:
    dialog = Dialog(False)
    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), _turn(dialog))

    await gate_tool_call(request, execute, modes={"echo": "allow"})

    assert execute.requests == [request]
    assert not dialog.calls
    assert _outcomes(tmp_path) == []


async def test_ask_ok_runs(tmp_path: Path) -> None:
    dialog = Dialog(True)
    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), _turn(dialog))

    await gate_tool_call(request, execute, modes={"echo": "ask"})

    assert execute.requests == [request]
    assert dialog.calls == [("echo", {"text": "x"}, "ask")]
    assert _outcomes(tmp_path) == []


async def test_cancel_is_denied(tmp_path: Path) -> None:
    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), _turn(Dialog(False)))

    result = await gate_tool_call(request, execute, modes={"echo": "ask"})

    assert not execute.requests
    _assert_denial(result, DENY_USER)
    assert _outcomes(tmp_path) == ["denied"]


async def test_timeout_is_denied_with_dialog_wait_in_duration(tmp_path: Path) -> None:
    """A dialog timing out answers False; the duration includes the wait."""
    execute = Execute()
    dialog = Dialog(False, delay=0.2)
    request = _request("echo", {"text": "x"}, _tool("echo"), _turn(dialog))

    result = await gate_tool_call(request, execute, modes={"echo": "ask_session"})

    _assert_denial(result, DENY_USER)
    (line,) = _log_lines(tmp_path)
    assert line["outcome"] == "denied"
    assert line["duration_s"] >= 0.2
    assert line["params"] == {"text": "x"}


async def test_no_turn_permissions_fails_closed(tmp_path: Path) -> None:
    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), None)

    result = await gate_tool_call(request, execute, modes={"echo": "ask"})

    assert not execute.requests
    _assert_denial(result, DENY_UNAVAILABLE)
    assert _outcomes(tmp_path) == ["denied"]


async def test_raising_confirm_is_dialog_error(tmp_path: Path) -> None:
    async def broken(_name: str, _args: dict[str, Any], _mode: PermissionMode) -> bool:
        raise RuntimeError("no UI")

    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), _turn(broken))

    result = await gate_tool_call(request, execute, modes={"echo": "ask"})

    assert not execute.requests
    _assert_denial(result, DENY_UNAVAILABLE)
    assert _outcomes(tmp_path) == ["dialog_error"]


async def test_cancel_during_dialog_logs_cancelled(tmp_path: Path) -> None:
    dialog = Dialog(True, delay=60)
    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), _turn(dialog))
    task = asyncio.create_task(gate_tool_call(request, execute, modes={"echo": "ask"}))
    await dialog.entered.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not execute.requests
    assert _outcomes(tmp_path) == ["cancelled"]


async def test_cancel_while_waiting_for_lock_logs_cancelled(tmp_path: Path) -> None:
    dialog = Dialog(True)
    turn = _turn(dialog)
    execute = Execute()
    request = _request("echo", {"text": "x"}, _tool("echo"), turn)
    await turn.lock.acquire()
    try:
        task = asyncio.create_task(
            gate_tool_call(request, execute, modes={"echo": "ask"})
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        turn.lock.release()

    assert not dialog.calls
    assert not execute.requests
    assert _outcomes(tmp_path) == ["cancelled"]


# --- ask_session grants -----------------------------------------------------------


async def test_ask_session_asks_once_per_grants_set() -> None:
    dialog = Dialog(True)
    grants: set[str] = set()
    tool = _tool("echo")
    execute = Execute()
    modes: dict[str, PermissionMode] = {"echo": "ask_session"}

    for call_id in ("call-1", "call-2"):
        request = _request("echo", {"text": "x"}, tool, _turn(dialog, grants), call_id)
        await gate_tool_call(request, execute, modes=modes)

    assert len(dialog.calls) == 1
    assert len(execute.requests) == 2
    assert grants == {"echo"}

    fresh = _request("echo", {"text": "x"}, tool, _turn(dialog, set()), "call-3")
    await gate_tool_call(fresh, execute, modes=modes)
    assert len(dialog.calls) == 2


async def test_ask_session_cancel_is_not_remembered() -> None:
    dialog = Dialog(False, True)
    grants: set[str] = set()
    tool = _tool("echo")
    execute = Execute()
    modes: dict[str, PermissionMode] = {"echo": "ask_session"}

    first = _request("echo", {"text": "x"}, tool, _turn(dialog, grants), "call-1")
    result = await gate_tool_call(first, execute, modes=modes)
    _assert_denial(result, DENY_USER)
    assert not grants

    second = _request("echo", {"text": "x"}, tool, _turn(dialog, grants), "call-2")
    await gate_tool_call(second, execute, modes=modes)
    assert len(dialog.calls) == 2
    assert execute.requests == [second]


async def test_ask_grants_nothing() -> None:
    dialog = Dialog(True)
    turn = _turn(dialog)
    tool = _tool("echo")
    execute = Execute()

    for call_id in ("call-1", "call-2"):
        request = _request("echo", {"text": "x"}, tool, turn, call_id)
        await gate_tool_call(request, execute, modes={"echo": "ask"})

    assert len(dialog.calls) == 2
    assert not turn.grants


# --- dialog lock --------------------------------------------------------------------


async def test_concurrent_ask_dialogs_do_not_overlap() -> None:
    dialog = Dialog(True, delay=0.05)
    turn = _turn(dialog)
    execute = Execute()
    modes: dict[str, PermissionMode] = {"a": "ask", "b": "ask"}

    await asyncio.gather(
        gate_tool_call(
            _request("a", {"text": "x"}, _tool("a"), turn, "call-1"), execute, modes
        ),
        gate_tool_call(
            _request("b", {"text": "x"}, _tool("b"), turn, "call-2"), execute, modes
        ),
    )

    assert len(dialog.events) == 4
    assert [event.split()[0] for event in dialog.events] == [
        "enter",
        "exit",
        "enter",
        "exit",
    ]
    assert len(execute.requests) == 2


async def test_concurrent_ask_session_calls_confirm_once() -> None:
    dialog = Dialog(True, delay=0.05)
    turn = _turn(dialog)
    tool = _tool("echo")
    execute = Execute()
    modes: dict[str, PermissionMode] = {"echo": "ask_session"}

    await asyncio.gather(
        gate_tool_call(
            _request("echo", {"text": "1"}, tool, turn, "c1"), execute, modes
        ),
        gate_tool_call(
            _request("echo", {"text": "2"}, tool, turn, "c2"), execute, modes
        ),
    )

    assert len(dialog.calls) == 1
    assert len(execute.requests) == 2


# --- graph level --------------------------------------------------------------------


def _calling(*calls: tuple[str, dict[str, Any]]) -> Any:
    """Return a model asking for *calls* (name, args) on call 1, then ``done``."""

    def script(n: int) -> AIMessage:
        if n == 1:
            tool_calls = [
                {"name": name, "args": args, "id": f"call-{i}"}
                for i, (name, args) in enumerate(calls, 1)
            ]
            return AIMessage(content="", tool_calls=tool_calls)
        return AIMessage(content="done")

    return make_scripted_chat_model(script, "fake")


async def _run(
    model: Any,
    tools: list[StructuredTool],
    modes: dict[str, PermissionMode],
    turn: TurnPermissions | None,
) -> dict[str, ToolMessage]:
    """Run one graph turn; return the tool messages by call id."""
    graph = agent.build_graph(model, tools, InMemorySaver(), modes=modes)
    configurable: dict[str, Any] = {"thread_id": "t1"}
    if turn is not None:
        configurable[TURN_PERMISSIONS_KEY] = turn
    result = await graph.ainvoke(
        {"messages": [HumanMessage("go")]}, {"configurable": configurable}
    )
    assert result["messages"][-1].content == "done"
    return {m.tool_call_id: m for m in result["messages"] if isinstance(m, ToolMessage)}


async def test_graph_allow_and_ask_ok_run() -> None:
    ran: list[str] = []
    tools = [_tool("free", ran), _tool("guarded", ran)]
    dialog = Dialog(True)
    model = _calling(("free", {"text": "a"}), ("guarded", {"text": "b"}))

    messages = await _run(
        model, tools, {"free": "allow", "guarded": "ask"}, _turn(dialog)
    )

    assert sorted(ran) == ["free", "guarded"]
    assert messages["call-1"].content == "free: a"
    assert messages["call-2"].content == "guarded: b"
    assert [name for name, _, _ in dialog.calls] == ["guarded"]


async def test_graph_cancel_denies_one_call_and_runs_the_other(tmp_path: Path) -> None:
    ran: list[str] = []
    tools = [_tool("free", ran), _tool("guarded", ran)]
    model = _calling(("free", {"text": "a"}), ("guarded", {"text": "b"}))

    messages = await _run(
        model, tools, {"free": "allow", "guarded": "ask"}, _turn(Dialog(False))
    )

    assert ran == ["free"]
    assert messages["call-1"].content == "free: a"
    _assert_denial(messages["call-2"], DENY_USER, "call-2")
    assert _outcomes(tmp_path) == ["denied"]


async def test_graph_deny_tool_gets_invalid_tool_text(tmp_path: Path) -> None:
    ran: list[str] = []
    tools = [_tool("free", ran)]
    modes: dict[str, PermissionMode] = {
        "free": "allow",
        "secret": "deny",
        "hidden": "deny",
    }
    model = _calling(("secret", {"text": "a"}))

    messages = await _run(model, tools, modes, _turn(Dialog()))

    message = messages["call-1"]
    assert message.status == "error"
    content = str(message.content)
    assert "secret" in content
    assert "free" in content
    assert "hidden" not in content
    assert not ran
    assert _outcomes(tmp_path) == ["blocked"]


def test_sync_invoke_runs_no_tool(tmp_path: Path) -> None:
    """The sync path has no approval prompt: even an ``allow`` tool is refused."""
    ran: list[str] = []
    # ToolNode.invoke needs a graph runtime: a one-node graph provides it.
    graph = StateGraph(MessagesState)
    graph.add_node("tools", make_tool_node([_tool("free", ran)], {"free": "allow"}))
    graph.add_edge(START, "tools")
    call = {"name": "free", "args": {"text": "a"}, "id": "call-1"}

    result = graph.compile().invoke(
        {"messages": [AIMessage(content="", tool_calls=[call])]}
    )

    assert not ran
    message = result["messages"][-1]
    _assert_denial(message, DENY_UNAVAILABLE)
    assert _outcomes(tmp_path) == ["denied"]


@pytest.mark.parametrize(
    "modes",
    [{}, {"free": "deny"}],
    ids=["missing", "deny"],
)
def test_build_graph_rejects_unbindable_tool(modes: dict[str, PermissionMode]) -> None:
    model = _calling()
    with pytest.raises(ValueError, match="bound tool 'free'"):
        agent.build_graph(model, [_tool("free")], InMemorySaver(), modes=modes)
