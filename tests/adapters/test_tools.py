"""Tests for to_structured_tool: a ToolSpec as a LangChain tool."""

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from mcp_coder_utils.tool_spec import ToolSpec, tool_spec
from pydantic import ValidationError

from agent_workbench.adapters.tools import to_structured_tool


def _sync_spec(result: Any) -> ToolSpec:
    """Return a sync spec whose tool echoes *count* next to *result*."""

    def lookup(count: int) -> Any:
        """Look something up."""
        return {"count": count, "result": result}

    return tool_spec(lookup, group="test.read", read_only=True)


def _async_spec(result: Any) -> ToolSpec:
    """Return an async spec whose tool echoes *count* next to *result*."""

    async def lookup(count: int) -> Any:
        """Look something up."""
        return {"count": count, "result": result}

    return tool_spec(lookup, group="test.read", read_only=True)


def _plain_spec(result: Any, is_async: bool) -> ToolSpec:
    """Return a sync or async spec whose tool returns *result* unchanged."""

    def fetch() -> Any:
        """Fetch something."""
        return result

    async def afetch() -> Any:
        """Fetch something."""
        return result

    return tool_spec(
        afetch if is_async else fetch, group="test.read", read_only=True, name="fetch"
    )


async def _invoke(spec: ToolSpec, args: dict[str, Any]) -> Any:
    """Invoke *spec* as a tool call, the way the graph does."""
    tool = to_structured_tool(spec)
    return await tool.ainvoke(
        {"type": "tool_call", "name": spec.name, "args": args, "id": "c1"}
    )


@pytest.mark.parametrize("make_spec", [_sync_spec, _async_spec])
async def test_tool_call_returns_tool_message(make_spec: Any) -> None:
    """Sync and async specs both answer a tool call with a ToolMessage of the JSON text."""
    message = await _invoke(make_spec("ok"), {"count": 2})

    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "c1"
    assert message.content == '{"count": 2, "result": "ok"}'


@pytest.mark.parametrize("is_async", [False, True])
@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("plain", "plain"),
        ({"a": 1}, '{"a": 1}'),
        (["a", "b"], '["a", "b"]'),
        ([], "[]"),
        (False, "false"),
    ],
)
async def test_tool_result_becomes_text(
    result: Any, expected: str, is_async: bool
) -> None:
    """Every result reaches the model as one string; lists are not content blocks."""
    message = await _invoke(_plain_spec(result, is_async), {})

    assert message.content == expected


@pytest.mark.parametrize("make_spec", [_sync_spec, _async_spec])
def test_spec_fields_carried_over(make_spec: Any) -> None:
    """Name, description and the args model are taken from the spec."""
    spec = make_spec("ok")

    tool = to_structured_tool(spec)

    assert tool.name == spec.name
    assert tool.description == spec.description
    assert tool.args_schema is spec.args_model


@pytest.mark.parametrize("make_spec", [_sync_spec, _async_spec])
async def test_invalid_arguments_raise(make_spec: Any) -> None:
    """Arguments that fail the args model raise a validation error."""
    with pytest.raises(ValidationError):
        await _invoke(make_spec("ok"), {"count": "not a number"})
