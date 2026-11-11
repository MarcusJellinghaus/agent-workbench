"""``build_graph`` (model node -> ToolNode) and the process-wide ``get_runtime``."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool, tool
from langgraph.checkpoint.memory import InMemorySaver

from agent_workbench.apps import agent
from agent_workbench.core.config import LLMConfig
from tests.langchain_doubles import make_scripted_chat_model


def _echo(text: str) -> str:
    """Return *text* unchanged."""
    return text


echo = tool(_echo)


def _answer(text: str) -> Any:
    return make_scripted_chat_model(lambda _n: AIMessage(content=text), "fake")


def test_empty_tool_list_does_not_bind_tools() -> None:
    model = _answer("hi")
    with patch.object(type(model), "bind_tools") as spy:
        agent.build_graph(model, [], InMemorySaver())
    spy.assert_not_called()


def test_tools_are_bound_once() -> None:
    model = _answer("hi")
    with patch.object(type(model), "bind_tools", return_value=model) as spy:
        agent.build_graph(model, [echo], InMemorySaver())
    spy.assert_called_once_with([echo])


async def test_plain_answer_ends_the_run() -> None:
    graph = agent.build_graph(_answer("hello"), [], InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}
    result = await graph.ainvoke({"messages": [HumanMessage("hi")]}, config)
    assert [m.type for m in result["messages"]] == ["human", "ai"]
    assert result["messages"][-1].content == "hello"


async def test_unknown_tool_call_routes_to_tool_node() -> None:
    def script(n: int) -> AIMessage:
        if n == 1:
            call = {"name": "missing", "args": {}, "id": "call-1"}
            return AIMessage(content="", tool_calls=[call])
        return AIMessage(content="done")

    model = make_scripted_chat_model(script, "fake")
    graph = agent.build_graph(model, [], InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}
    result = await graph.ainvoke({"messages": [HumanMessage("hi")]}, config)

    messages = result["messages"]
    assert [m.type for m in messages] == ["human", "ai", "tool", "ai"]
    tool_message = messages[2]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "error"
    assert tool_message.tool_call_id == "call-1"
    assert messages[-1].content == "done"
    assert model.invoke_count == 2


def _fail(text: str) -> str:
    """Raise ``ValueError("boom")``."""
    raise ValueError("boom")


async def test_tool_exception_becomes_error_message() -> None:
    fail = StructuredTool.from_function(_fail, name="fail")

    def script(n: int) -> AIMessage:
        if n == 1:
            call = {"name": "fail", "args": {"text": "x"}, "id": "call-1"}
            return AIMessage(content="", tool_calls=[call])
        return AIMessage(content="done")

    model = make_scripted_chat_model(script, "fake")
    graph = agent.build_graph(model, [fail], InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}
    result = await graph.ainvoke({"messages": [HumanMessage("hi")]}, config)

    messages = result["messages"]
    assert [m.type for m in messages] == ["human", "ai", "tool", "ai"]
    tool_message = messages[2]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "error"
    assert "boom" in str(tool_message.content)
    assert messages[-1].content == "done"
    assert model.invoke_count == 2


async def test_get_runtime_builds_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(agent, "_runtime", None)
    llm_config = LLMConfig(backend="openai", model="gpt-4o")
    model = _answer("hi")
    with (
        patch("agent_workbench.adapters.config.app_data_dir", return_value=tmp_path),
        patch.object(agent, "load_llm_config", return_value=llm_config),
        patch.object(agent, "create_chat_model", return_value=model) as create,
    ):
        try:
            first = await agent.get_runtime()
            second = await agent.get_runtime()
        finally:
            await agent.close_runtime()

    assert second is first
    assert first.chat_model is model
    assert first.llm_config is llm_config
    assert first.checkpointer is not None
    create.assert_called_once_with(llm_config, agent.MODEL_TIMEOUT)
