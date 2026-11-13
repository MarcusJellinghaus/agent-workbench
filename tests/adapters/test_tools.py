"""Tests for to_structured_tool and build_toolsets."""

import logging
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from mcp_coder_utils.tool_spec import ToolSpec, tool_spec
from pydantic import ValidationError

from agent_workbench.adapters.config import ConfigFile, read_config_file
from agent_workbench.adapters.tools import Toolsets, build_toolsets, to_structured_tool
from tests.adapters.tool_fixtures import (
    FakeToolset,
    new_provider,
    register_providers,
    write_config_file,
)


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


def test_build_toolsets_merges_specs_in_config_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two providers → their specs merged in config order; both toolsets kept."""
    sql, workspace = new_provider(), new_provider()
    register_providers(monkeypatch, {"sql": sql, "workspace": workspace})
    path = write_config_file(
        tmp_path,
        {
            "workspace": {"tools": ["read_file"], "async": True},
            "sql": {"tools": ["query", "list_tables"]},
        },
    )

    toolsets = build_toolsets(read_config_file(path))

    assert [spec.name for spec in toolsets.specs] == [
        "read_file",
        "query",
        "list_tables",
    ]
    assert toolsets.toolsets == (workspace.built[0], sql.built[0])


def test_build_toolsets_passes_table_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider gets its ``[tools.<name>]`` table as its config."""
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    path = write_config_file(tmp_path, {"fake": {"group": "fake.update"}})

    toolsets = build_toolsets(read_config_file(path))

    assert [spec.group for spec in toolsets.specs] == ["fake.update"]


def test_build_toolsets_no_tools(tmp_path: Path) -> None:
    """No ``[tools]`` → no specs, nothing to close."""
    toolsets = build_toolsets(read_config_file(write_config_file(tmp_path, {})))

    assert toolsets == Toolsets(())


def test_close_closes_every_toolset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``close()`` closes both toolsets."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    path = write_config_file(tmp_path, {"first": {}, "second": {"tools": ["other"]}})

    build_toolsets(read_config_file(path)).close()

    assert first.built[0].closed
    assert second.built[0].closed


def test_close_failure_logged_rest_closed(caplog: pytest.LogCaptureFixture) -> None:
    """One ``close`` raising → logged, the other toolset still closed."""
    failing = FakeToolset((), close_error="boom")
    other = FakeToolset(())

    with caplog.at_level(logging.WARNING, logger="agent_workbench.adapters.tools"):
        Toolsets((), (failing, other)).close()

    assert failing.closed
    assert other.closed
    assert "boom" in caplog.text


def test_duplicate_tool_name_closes_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same tool name in two providers → ValueError; the built toolsets closed."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    path = write_config_file(tmp_path, {"first": {}, "second": {}})

    with pytest.raises(ValueError, match="duplicate tool name 'echo'"):
        build_toolsets(read_config_file(path))

    assert first.built[0].closed
    assert second.built[0].closed


def test_build_failure_closes_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second provider's ``build`` raising → ValueError; the first toolset closed."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    path = write_config_file(tmp_path, {"first": {}, "second": {"fail": "no file"}})

    with pytest.raises(ValueError, match=r"\[tools.second\].*no file"):
        build_toolsets(read_config_file(path))

    assert first.built[0].closed
    assert not second.built


def test_unregistered_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unregistered ``[tools.x]`` → ValueError naming the registered providers."""
    provider = new_provider()
    register_providers(monkeypatch, {"sql": provider})
    path = write_config_file(tmp_path, {"sql": {}, "x": {}})

    with pytest.raises(ValueError, match="'x'.*registered: sql"):
        build_toolsets(read_config_file(path))

    assert provider.built[0].closed


@pytest.mark.parametrize(
    ("tools", "tools_type_error", "label"),
    [
        ({"x": 1}, None, r"\[tools.x\]"),
        ({}, "expected table, got str", r"\[tools\]"),
    ],
)
def test_shape_error_loads_no_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tools: dict[str, Any],
    tools_type_error: str | None,
    label: str,
) -> None:
    """A ``[tools]`` shape error → ValueError naming the table; no provider loaded."""
    stubs = register_providers(monkeypatch, {"x": new_provider()})
    config_file = ConfigFile(
        tmp_path / "config.toml",
        True,
        None,
        {},
        tools=tools,
        tools_type_error=tools_type_error,
    )

    with pytest.raises(ValueError, match=rf"Invalid \[tools\] config: {label}"):
        build_toolsets(config_file)

    assert not stubs[0].loads
