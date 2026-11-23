"""``run_turn``: streaming, final-message fallback, limits, timeouts, errors, Stop, usage,
per-turn permissions."""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self
from unittest.mock import patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import NodeCancelledError

from agent_workbench.adapters import llm
from agent_workbench.apps import agent
from agent_workbench.apps.permission_gate import (
    DENY_UNAVAILABLE,
    TURN_PERMISSIONS_KEY,
    TurnPermissions,
)
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.permissions import PermissionMode
from agent_workbench.core.types import TokenUsage
from tests.langchain_doubles import make_scripted_chat_model

LLM_CONFIG = LLMConfig(backend="openai", model="gpt-4o")


class _StallingModel(BaseChatModel):  # type: ignore[misc]
    """Chat model returning ``replies`` in order, then never returning.

    ``entered`` is set once it is waiting.
    """

    entered: Any = None
    raise_exc: Any = None
    replies: list[AIMessage] = []

    def bind_tools(self, tools: Any, **kw: Any) -> Self:
        return self

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("stalling model implements _agenerate")

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.replies:
            return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])
        if self.entered is not None:
            self.entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    @property
    def _llm_type(self) -> str:
        return "stalling"


class _RecordingModel(BaseChatModel):  # type: ignore[misc]
    """Chat model answering ``answer-<n>`` and recording each call's input messages."""

    calls: list[list[BaseMessage]] = []

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("recording model implements _agenerate")

    async def _agenerate(
        self, messages: list[BaseMessage], *args: Any, **kwargs: Any
    ) -> ChatResult:
        self.calls.append(list(messages))
        message = AIMessage(content=f"answer-{len(self.calls)}")
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "recording"


def _graph(
    model: Any, tools: Sequence[Any] = (), mode: PermissionMode = "allow"
) -> Any:
    modes: dict[str, PermissionMode] = {tool.name: mode for tool in tools}
    return agent.build_graph(model, tools, InMemorySaver(), modes=modes)


async def _turn(
    graph: Any,
    model: Any,
    text: str,
    collected: list[str],
    token_usage: TokenUsage | None = None,
    **kwargs: Any,
) -> str | None:
    async def on_text(delta: str) -> None:
        collected.append(delta)

    return await agent.run_turn(
        graph,
        model,
        LLM_CONFIG,
        text,
        "thread-1",
        on_text,
        token_usage if token_usage is not None else TokenUsage(),
        **kwargs,
    )


def _tool_call(n: int, name: str = "missing", **args: Any) -> AIMessage:
    call = {"name": name, "args": args, "id": f"call-{n}"}
    return AIMessage(content="", tool_calls=[call])


def _call_then_answer(name: str, **args: Any) -> Any:
    """Scripted model calling tool *name* once, then answering "done"."""

    def script(n: int) -> AIMessage:
        return _tool_call(n, name, **args) if n == 1 else AIMessage(content="done")

    return make_scripted_chat_model(script, "fake")


class _Recorder:
    """Records the tool callbacks as ``(kind, run_id, ...)`` tuples."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def on_tool_start(self, run_id: str, name: str, args: dict[str, Any]) -> None:
        self.calls.append(("start", run_id, name, args))

    async def on_tool_end(self, run_id: str, output: str) -> None:
        self.calls.append(("end", run_id, output))


async def _slow(text: str) -> str:
    """Sleep 0.3 s, then return *text*."""
    await asyncio.sleep(0.3)
    return text


def _echo(text: str) -> str:
    """Return *text* unchanged."""
    return text


def _fail(text: str) -> str:
    """Raise ``ValueError("boom")``."""
    raise ValueError("boom")


slow = StructuredTool.from_function(coroutine=_slow, name="slow")
echo = StructuredTool.from_function(_echo, name="echo")
fail = StructuredTool.from_function(_fail, name="fail")


async def test_tool_run_pauses_the_idle_timer() -> None:
    model = _call_then_answer("slow", text="x")
    collected: list[str] = []
    message = await _turn(
        _graph(model, [slow]),
        model,
        "hi",
        collected,
        idle_timeout=0.1,
        overall_timeout=5,
    )
    assert message is None
    assert collected == ["done"]


async def test_stalling_model_after_a_tool_hits_the_idle_limit() -> None:
    model = _StallingModel(replies=[_tool_call(1, "echo", text="x")])
    with patch.object(llm, "map_provider_error") as spy:
        message = await _turn(
            _graph(model, [echo]), model, "hi", [], idle_timeout=0.1, overall_timeout=5
        )
    assert message == agent._IDLE_MSG.format(s=0.1)
    spy.assert_not_called()


async def test_tool_callbacks_fire_once_with_the_same_run_id() -> None:
    model = _call_then_answer("echo", text="hello")
    recorder = _Recorder()
    message = await _turn(
        _graph(model, [echo]),
        model,
        "hi",
        [],
        on_tool_start=recorder.on_tool_start,
        on_tool_end=recorder.on_tool_end,
    )
    assert message is None
    run_id = recorder.calls[0][1]
    assert recorder.calls == [
        ("start", run_id, "echo", {"text": "hello"}),
        ("end", run_id, "hello"),
    ]


async def test_failing_tool_emits_tool_error_as_end() -> None:
    model = _call_then_answer("fail", text="x")
    recorder = _Recorder()
    message = await _turn(
        _graph(model, [fail]),
        model,
        "hi",
        [],
        on_tool_start=recorder.on_tool_start,
        on_tool_end=recorder.on_tool_end,
    )
    assert message is None
    # The tool raises, so langchain_core emits on_tool_error (no on_tool_end); the
    # ToolNode then turns the exception into an error ToolMessage.
    run_id = recorder.calls[0][1]
    assert recorder.calls == [
        ("start", run_id, "fail", {"text": "x"}),
        ("end", run_id, "boom"),
    ]


async def test_stop_while_a_tool_awaits_propagates_cancel() -> None:
    entered = asyncio.Event()

    async def _wait(text: str) -> str:
        """Wait forever."""
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    wait = StructuredTool.from_function(coroutine=_wait, name="wait")
    model = _call_then_answer("wait", text="x")
    with patch.object(llm, "map_provider_error") as spy:
        task = asyncio.create_task(_turn(_graph(model, [wait]), model, "hi", []))
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    spy.assert_not_called()


async def test_plain_answer_arrives_once() -> None:
    model = make_scripted_chat_model(lambda _n: AIMessage(content="hello"), "fake")
    collected: list[str] = []
    assert await _turn(_graph(model), model, "hi", collected) is None
    assert collected == ["hello"]


async def test_streamed_answer_is_not_repeated() -> None:
    model = GenericFakeChatModel(messages=iter([AIMessage(content="hello big world")]))
    collected: list[str] = []
    assert await _turn(_graph(model), model, "hi", collected) is None
    assert len(collected) > 1
    assert "".join(collected) == "hello big world"


async def test_second_turn_sees_the_first() -> None:
    model = _RecordingModel(calls=[])
    graph = _graph(model)
    collected: list[str] = []
    assert await _turn(graph, model, "one", collected) is None
    assert await _turn(graph, model, "two", collected) is None

    state = await graph.aget_state({"configurable": {"thread_id": "thread-1"}})
    messages = state.values["messages"]
    assert [m.type for m in messages] == ["human", "ai", "human", "ai"]
    assert [m.content for m in model.calls[1]] == ["one", "answer-1", "two"]
    assert collected == ["answer-1", "answer-2"]


async def test_step_limit_aborts_and_thread_continues() -> None:
    stop_calling = False

    def script(n: int) -> AIMessage:
        return AIMessage(content="recovered") if stop_calling else _tool_call(n)

    model = make_scripted_chat_model(script, "fake")
    graph = _graph(model)
    collected: list[str] = []
    message = await _turn(graph, model, "loop", collected)
    assert message is not None
    assert "Step limit" in message
    assert message == agent._STEPS_MSG.format(n=agent.AGENT_MAX_STEPS)

    stop_calling = True
    assert await _turn(graph, model, "again", collected) is None
    assert collected[-1] == "recovered"


async def test_provider_error_is_mapped() -> None:
    boom = ConnectionError("raw")

    def script(_n: int) -> AIMessage:
        raise boom

    model = make_scripted_chat_model(script, "fake")
    with patch.object(
        llm, "map_provider_error", side_effect=RuntimeError("mapped")
    ) as spy:
        message = await _turn(_graph(model), model, "hi", [])
    assert message == "Error: mapped"
    spy.assert_called_once_with(boom, LLM_CONFIG, model)


async def test_provider_timeout_error_is_mapped() -> None:
    boom = TimeoutError("provider")

    def script(_n: int) -> AIMessage:
        raise boom

    model = make_scripted_chat_model(script, "fake")
    with patch.object(
        llm, "map_provider_error", side_effect=RuntimeError("mapped")
    ) as spy:
        message = await _turn(_graph(model), model, "hi", [])
    assert message == "Error: mapped"
    spy.assert_called_once_with(boom, LLM_CONFIG, model)


async def test_inactivity_timeout() -> None:
    model = _StallingModel()
    with patch.object(llm, "map_provider_error") as spy:
        message = await _turn(_graph(model), model, "hi", [], idle_timeout=0.05)
    assert message == agent._IDLE_MSG.format(s=0.05)
    spy.assert_not_called()


async def test_overall_timeout() -> None:
    model = _StallingModel()
    with patch.object(llm, "map_provider_error") as spy:
        message = await _turn(
            _graph(model), model, "hi", [], idle_timeout=5, overall_timeout=0.05
        )
    assert message == agent._OVERALL_MSG.format(s=0.05)
    spy.assert_not_called()


async def test_stop_propagates_cancel() -> None:
    entered = asyncio.Event()
    model = _StallingModel(entered=entered)
    collected: list[str] = []
    with patch.object(llm, "map_provider_error") as spy:
        task = asyncio.create_task(_turn(_graph(model), model, "hi", collected))
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not collected
    spy.assert_not_called()


async def test_node_cancelled_error_becomes_cancel() -> None:
    # A CancelledError raised inside _agenerate is not wrapped by langgraph (langchain_core
    # turns it into an AttributeError first), so the model raises NodeCancelledError itself.
    model = _StallingModel(raise_exc=NodeCancelledError("model"))
    with patch.object(llm, "map_provider_error") as spy:
        with pytest.raises(asyncio.CancelledError) as info:
            await _turn(_graph(model), model, "hi", [])
    assert isinstance(info.value.__cause__, NodeCancelledError)
    spy.assert_not_called()


def _with_usage(message: AIMessage, inp: int, out: int, cache: int) -> AIMessage:
    message.usage_metadata = {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "input_token_details": {"cache_read": cache},
    }
    return message


async def test_usage_per_turn_and_session() -> None:
    def script(n: int) -> AIMessage:
        if n % 2:
            return _with_usage(_tool_call(n), 10, 1, 4)
        return _with_usage(AIMessage(content="done"), 20, 2, 8)

    model = make_scripted_chat_model(script, "fake")
    graph = _graph(model)
    token_usage = TokenUsage()

    assert await _turn(graph, model, "one", [], token_usage) is None
    assert (token_usage.last_input, token_usage.last_output) == (30, 3)
    assert token_usage.last_cache_read == 12

    assert await _turn(graph, model, "two", [], token_usage) is None
    assert (token_usage.total_input, token_usage.total_output) == (60, 6)
    assert token_usage.total_cache_read == 24


async def test_failed_turn_leaves_usage_unchanged() -> None:
    def script(n: int) -> AIMessage:
        if n == 1:
            return _with_usage(_tool_call(n), 10, 1, 0)
        raise ConnectionError("raw")

    model = make_scripted_chat_model(script, "fake")
    token_usage = TokenUsage()
    with patch.object(llm, "map_provider_error", side_effect=RuntimeError("mapped")):
        message = await _turn(_graph(model), model, "hi", [], token_usage)
    assert message == "Error: mapped"
    assert token_usage == TokenUsage()


# --- per-turn permissions -------------------------------------------------------------


class _Confirm:
    """Confirm callback answering after *delay* seconds; records its calls.

    Answers OK, except Cancel for the tools named in *cancel*.
    """

    def __init__(self, delay: float = 0.0, cancel: Sequence[str] = ()) -> None:
        self.delay = delay
        self.cancel = set(cancel)
        self.calls: list[tuple[str, dict[str, Any], PermissionMode]] = []
        self.entered = asyncio.Event()

    async def __call__(
        self, name: str, args: dict[str, Any], mode: PermissionMode
    ) -> bool:
        self.calls.append((name, args, mode))
        self.entered.set()
        await asyncio.sleep(self.delay)
        return name not in self.cancel


def _outcomes(tmp_path: Path) -> list[str]:
    """Return the outcomes in ``tool_calls.jsonl`` (app data is ``tmp_path``)."""
    path = tmp_path / "logs" / "tool_calls.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["outcome"] for line in lines]


async def _tool_messages(graph: Any) -> list[ToolMessage]:
    state = await graph.aget_state({"configurable": {"thread_id": "thread-1"}})
    return [m for m in state.values["messages"] if isinstance(m, ToolMessage)]


async def test_open_dialog_pauses_the_idle_timer() -> None:
    model = _call_then_answer("echo", text="x")
    graph = _graph(model, [echo], "ask")
    collected: list[str] = []
    message = await _turn(
        graph,
        model,
        "hi",
        collected,
        idle_timeout=0.1,
        overall_timeout=5,
        confirm=_Confirm(delay=0.3),
    )
    assert message is None
    assert collected == ["done"]
    (tool_message,) = await _tool_messages(graph)
    assert tool_message.status == "success"
    assert tool_message.content == "x"


async def test_dialog_ending_while_a_tool_runs_keeps_the_timer_paused() -> None:
    """Call A is approved and runs 0.3 s; call B's dialog closes meanwhile.

    B is cancelled, so no tool event of B re-pauses the timer after its dialog.
    """

    def script(n: int) -> AIMessage:
        if n > 1:
            return AIMessage(content="done")
        calls = [
            {"name": "slow", "args": {"text": "a"}, "id": "call-1"},
            {"name": "echo", "args": {"text": "b"}, "id": "call-2"},
        ]
        return AIMessage(content="", tool_calls=calls)

    model = make_scripted_chat_model(script, "fake")
    confirm = _Confirm(delay=0.03, cancel=["echo"])
    graph = _graph(model, [slow, echo], "ask")
    with patch.object(llm, "map_provider_error") as spy:
        message = await _turn(
            graph,
            model,
            "hi",
            [],
            idle_timeout=0.1,
            overall_timeout=5,
            confirm=confirm,
        )
    assert message is None
    spy.assert_not_called()
    assert [name for name, _, _ in confirm.calls] == ["slow", "echo"]
    messages = {m.tool_call_id: m for m in await _tool_messages(graph)}
    assert messages["call-1"].content == "a"
    assert messages["call-2"].status == "error"


async def test_without_confirm_an_ask_tool_is_denied(tmp_path: Path) -> None:
    model = _call_then_answer("echo", text="x")
    graph = _graph(model, [echo], "ask")
    assert await _turn(graph, model, "hi", []) is None
    (tool_message,) = await _tool_messages(graph)
    assert tool_message.status == "error"
    assert tool_message.content == DENY_UNAVAILABLE
    assert _outcomes(tmp_path) == ["denied"]


async def test_confirm_gets_the_call_and_the_gate_fills_the_passed_grants() -> None:
    model = _call_then_answer("echo", text="x")
    confirm = _Confirm()
    grants: set[str] = set()
    message = await _turn(
        _graph(model, [echo], "ask_session"),
        model,
        "hi",
        [],
        confirm=confirm,
        grants=grants,
    )
    assert message is None
    assert confirm.calls == [("echo", {"text": "x"}, "ask_session")]
    assert grants == {"echo"}


async def test_turn_permissions_are_not_checkpointed() -> None:
    saver = InMemorySaver()
    model = _call_then_answer("echo", text="x")
    graph = agent.build_graph(model, [echo], saver, modes={"echo": "ask"})
    assert await _turn(graph, model, "hi", [], confirm=_Confirm()) is None
    checkpoint = await saver.aget_tuple({"configurable": {"thread_id": "thread-1"}})
    assert checkpoint is not None
    metadata = checkpoint.metadata
    assert TURN_PERMISSIONS_KEY not in metadata
    assert not any(
        callable(value) or isinstance(value, TurnPermissions)
        for value in metadata.values()
    )


async def test_stop_during_a_dialog_propagates_cancel(tmp_path: Path) -> None:
    confirm = _Confirm(delay=60)
    model = _call_then_answer("echo", text="x")
    graph = _graph(model, [echo], "ask")
    with patch.object(llm, "map_provider_error") as spy:
        task = asyncio.create_task(_turn(graph, model, "hi", [], confirm=confirm))
        await asyncio.wait_for(confirm.entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    spy.assert_not_called()
    assert _outcomes(tmp_path) == ["cancelled"]
