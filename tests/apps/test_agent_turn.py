"""``run_turn``: streaming, final-message fallback, limits, timeouts, errors, Stop, usage."""

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import NodeCancelledError

from agent_workbench.adapters import llm
from agent_workbench.apps import agent
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.types import TokenUsage
from tests.langchain_doubles import make_scripted_chat_model

LLM_CONFIG = LLMConfig(backend="openai", model="gpt-4o")


class _StallingModel(BaseChatModel):  # type: ignore[misc]
    """Chat model whose call never returns; ``entered`` is set once it is waiting."""

    entered: Any = None
    raise_exc: Any = None

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("stalling model implements _agenerate")

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        if self.raise_exc is not None:
            raise self.raise_exc
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


def _graph(model: Any) -> Any:
    return agent.build_graph(model, [], InMemorySaver())


async def _turn(
    graph: Any,
    model: Any,
    text: str,
    collected: list[str],
    token_usage: TokenUsage | None = None,
    **timeouts: float,
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
        **timeouts,
    )


def _tool_call(n: int) -> AIMessage:
    call = {"name": "missing", "args": {}, "id": f"call-{n}"}
    return AIMessage(content="", tool_calls=[call])


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
