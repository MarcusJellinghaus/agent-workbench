"""Tools in the agent: the loop with a fake provider, the runtime wiring, real providers."""

import asyncio
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent_workbench.adapters.config import read_config_file
from agent_workbench.adapters.tools import Toolsets, build_toolsets
from agent_workbench.adapters.toolset_providers import registered_providers
from agent_workbench.apps import agent
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.types import TokenUsage
from tests.adapters.tool_fixtures import (
    new_provider,
    register_providers,
    write_config_file,
)
from tests.langchain_doubles import make_scripted_chat_model

LLM_CONFIG = LLMConfig(backend="openai", model="gpt-4o")

# The groups and names of tests/services/test_tool_filter.py, one provider per group.
_FILTER_TABLES: dict[str, dict[str, Any]] = {
    "schema": {"tools": ["read_tables"], "group": "sql.schema"},
    "validation": {"tools": ["validate_sql", "verify"], "group": "sql.validation"},
    "profiling": {"tools": ["profile_table"], "group": "sql.profiling"},
    "read": {"tools": ["read_file"], "group": "workspace.read"},
    "write": {"tools": ["save_file"], "group": "workspace.write"},
    "delete": {"tools": ["delete_this_file"], "group": "workspace.delete"},
}


@pytest.fixture
def app_data(tmp_path: Path) -> Iterator[Path]:
    """Point ``app_data_dir`` at *tmp_path*."""
    with patch("agent_workbench.adapters.config.app_data_dir", return_value=tmp_path):
        yield tmp_path


@pytest.fixture(name="fresh_runtime")
def _fresh_runtime(monkeypatch: pytest.MonkeyPatch, app_data: Path) -> None:
    """No runtime yet, and a lock bound to this test's loop."""
    monkeypatch.setattr(agent, "_runtime", None)
    monkeypatch.setattr(agent, "_runtime_lock", asyncio.Lock())


def _answer(text: str) -> Any:
    return make_scripted_chat_model(lambda _n: AIMessage(content=text), "fake")


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


async def _run_loop(toolsets: Toolsets, model: Any) -> dict[str, Any]:
    """Run one turn of *model* with the tools of *toolsets*; return what happened."""
    graph = agent.build_graph(model, agent.build_tools(toolsets), InMemorySaver())
    starts: list[tuple[str, str, dict[str, Any]]] = []
    ends: list[tuple[str, str]] = []

    async def on_tool_start(run_id: str, name: str, args: dict[str, Any]) -> None:
        starts.append((run_id, name, args))

    async def on_tool_end(run_id: str, output: str) -> None:
        ends.append((run_id, output))

    async def on_text(_delta: str) -> None:
        pass

    error = await agent.run_turn(
        graph,
        model,
        LLM_CONFIG,
        "go",
        "t1",
        on_text,
        TokenUsage(),
        on_tool_start=on_tool_start,
        on_tool_end=on_tool_end,
    )
    state = await graph.aget_state({"configurable": {"thread_id": "t1"}})
    tool_messages = {
        m.tool_call_id: m
        for m in state.values["messages"]
        if isinstance(m, ToolMessage)
    }
    return {"error": error, "starts": starts, "ends": ends, "tools": tool_messages}


def _log_lines(app_data: Path) -> list[dict[str, Any]]:
    path = app_data / "logs" / "tool_calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _spy_open() -> tuple[list[Any], Any]:
    """Return the list of opened savers and a spy for ``open_checkpointer``."""
    opened: list[Any] = []
    open_checkpointer = agent.open_checkpointer

    async def spy(path: Path) -> Any:
        opened.append(await open_checkpointer(path))
        return opened[-1]

    return opened, spy


async def _assert_closed(saver: Any) -> None:
    with pytest.raises(ValueError, match="no active connection"):
        await saver.conn.execute("SELECT 1")


async def test_agent_loop_runs_sync_and_async_tools(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both tool results reach the model, both calls are logged, callbacks fire."""
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    path = write_config_file(
        app_data,
        {
            "fake": {
                "tools": ["sync_echo", "async_echo"],
                "async_tools": ["async_echo"],
                "group": "workspace.read",
            }
        },
    )
    toolsets = build_toolsets(read_config_file(path))
    model = _calling(("sync_echo", {"text": "a"}), ("async_echo", {"text": "b"}))

    result = await _run_loop(toolsets, model)

    assert result["error"] is None
    assert model.invoke_count == 2
    assert result["tools"]["call-1"].content == "sync_echo: a"
    assert result["tools"]["call-2"].content == "async_echo: b"
    lines = _log_lines(app_data)
    assert sorted(line["tool"] for line in lines) == ["async_echo", "sync_echo"]
    assert [line["outcome"] for line in lines] == ["ok", "ok"]
    assert sorted(name for _, name, _ in result["starts"]) == [
        "async_echo",
        "sync_echo",
    ]
    assert sorted(output for _, output in result["ends"]) == [
        "async_echo: b",
        "sync_echo: a",
    ]


@pytest.mark.usefixtures("fresh_runtime")
async def test_only_enabled_tools_are_bound(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``get_runtime`` binds schema, ``validate_sql``, read and write tools only."""
    register_providers(monkeypatch, {name: new_provider() for name in _FILTER_TABLES})
    write_config_file(app_data, _FILTER_TABLES)
    model = _answer("hi")
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=model),
        patch.object(type(model), "bind_tools", return_value=model) as bind,
    ):
        try:
            await agent.get_runtime()
        finally:
            await agent.close_runtime()

    bind.assert_called_once()
    assert [tool.name for tool in bind.call_args.args[0]] == [
        "read_tables",
        "validate_sql",
        "read_file",
        "save_file",
    ]


@pytest.mark.usefixtures("fresh_runtime")
async def test_get_runtime_clamps_provider_loggers(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configured provider's top-level package is clamped."""
    register_providers(monkeypatch, {"fake": new_provider()})
    write_config_file(app_data, {"fake": {}})
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
        patch("agent_workbench.services.logging_setup.clamp_loggers") as clamp,
    ):
        try:
            await agent.get_runtime()
        finally:
            await agent.close_runtime()

    clamp.assert_called_once_with(["tests"])


@pytest.mark.usefixtures("fresh_runtime")
async def test_duplicate_tool_names_fail_get_runtime(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same tool name in two providers → ValueError; nothing left open."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    write_config_file(app_data, {"first": {}, "second": {}})
    opened, spy = _spy_open()
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
        patch.object(agent, "open_checkpointer", side_effect=spy),
        pytest.raises(ValueError, match="duplicate tool name 'echo'"),
    ):
        await agent.get_runtime()

    for saver in opened:
        await _assert_closed(saver)
    assert first.built[0].closed
    assert second.built[0].closed
    assert agent._runtime is None


@pytest.mark.usefixtures("fresh_runtime")
async def test_failure_after_build_closes_toolsets_and_checkpointer(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``build_graph`` raising → the toolsets and the checkpointer are closed."""
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    write_config_file(app_data, {"fake": {}})
    opened, spy = _spy_open()
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
        patch.object(agent, "open_checkpointer", side_effect=spy),
        patch.object(agent, "build_graph", side_effect=RuntimeError("no graph")),
        pytest.raises(RuntimeError, match="no graph"),
    ):
        await agent.get_runtime()

    assert len(opened) == 1
    await _assert_closed(opened[0])
    assert provider.built[0].closed
    assert agent._runtime is None


@pytest.mark.usefixtures("fresh_runtime")
async def test_close_runtime_closes_toolsets(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``close_runtime`` closes the toolsets kept in the runtime."""
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    write_config_file(app_data, {"fake": {}})
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
    ):
        try:
            runtime = await agent.get_runtime()
            assert runtime.toolsets is not None
            assert runtime.toolsets.toolsets == (provider.built[0],)
            assert not provider.built[0].closed
        finally:
            await agent.close_runtime()

    assert provider.built[0].closed


@pytest.mark.usefixtures("fresh_runtime")
async def test_close_runtime_closes_toolsets_when_connection_close_fails(
    app_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising ``conn.close`` propagates; the toolsets are still closed."""
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    write_config_file(app_data, {"fake": {}})
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
    ):
        runtime = await agent.get_runtime()
    conn = runtime.checkpointer.conn
    try:
        with (
            patch.object(conn, "close", side_effect=RuntimeError("conn close")),
            pytest.raises(RuntimeError, match="conn close"),
        ):
            await agent.close_runtime()
    finally:
        await conn.close()

    assert provider.built[0].closed
    assert agent._runtime is None


@pytest.mark.usefixtures("fresh_runtime")
async def test_no_tools_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``[tools]`` → no toolsets, no tools bound, no provider loaded."""
    stubs = register_providers(monkeypatch, {"fake": new_provider()})
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
        patch.object(agent, "build_graph", wraps=agent.build_graph) as build,
    ):
        try:
            runtime = await agent.get_runtime()
        finally:
            await agent.close_runtime()

    assert runtime.toolsets is None
    assert build.call_args.args[1] == []
    assert not stubs[0].loads


@pytest.mark.usefixtures("fresh_runtime")
async def test_non_table_tools_fails_get_runtime(app_data: Path) -> None:
    """``tools = "x"`` → ValueError; the checkpointer is not left open."""
    (app_data / "config.toml").write_text('tools = "x"\n', encoding="utf-8")
    opened, spy = _spy_open()
    with (
        patch.object(agent, "load_llm_config", return_value=LLM_CONFIG),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
        patch.object(agent, "open_checkpointer", side_effect=spy),
        pytest.raises(ValueError, match=r"Invalid \[tools\] config"),
    ):
        await agent.get_runtime()

    for saver in opened:
        await _assert_closed(saver)
    assert agent._runtime is None


_REAL_PROVIDERS = {"sql", "workspace"}


def _real_provider_configs(root: Path) -> dict[str, dict[str, Any]]:
    """Write a SQLite database with ``customers``, its configs and a workspace.

    Returns:
        The ``[tools.sql]`` and ``[tools.workspace]`` tables.
    """
    sql_dir = root / "sql"
    sql_dir.mkdir()
    db = sql_dir / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.close()
    query_config = sql_dir / "mcp-tools-sql.toml"
    query_config.write_text('connection = "default"\n', encoding="utf-8")
    # A temp database config, so ~/.mcp-tools-sql/config.toml is never read.
    database_config = sql_dir / "db.toml"
    database_config.write_text(
        f'[connections.default]\nbackend = "sqlite"\npath = "{db.as_posix()}"\n',
        encoding="utf-8",
    )
    workspace = root / "workspace"
    workspace.mkdir()
    return {
        "sql": {
            "query_config": query_config.as_posix(),
            "database_config": database_config.as_posix(),
        },
        "workspace": {"project_dir": workspace.as_posix()},
    }


@pytest.mark.integration
@pytest.mark.skipif(
    not _REAL_PROVIDERS.issubset(registered_providers()),
    reason="toolset providers 'sql' and 'workspace' are not installed",
)
async def test_agent_loop_with_real_providers(app_data: Path) -> None:
    """The model lists the tables and writes a report through the real tools."""
    path = write_config_file(app_data, _real_provider_configs(app_data))
    toolsets = build_toolsets(read_config_file(path))
    model = _calling(
        ("read_tables", {"schema": "main"}),
        ("save_file", {"file_path": "report.md", "content": "# Report"}),
    )
    try:
        result = await _run_loop(toolsets, model)
    finally:
        toolsets.close()

    assert result["error"] is None
    assert "customers" in str(result["tools"]["call-1"].content)
    report = app_data / "workspace" / "report.md"
    assert report.read_text(encoding="utf-8") == "# Report"
    assert [line["outcome"] for line in _log_lines(app_data)] == ["ok", "ok"]
