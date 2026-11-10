"""The persistent SQLite checkpointer: restart, ``secure_delete``, delete, runtime."""

import asyncio
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from agent_workbench.apps import agent
from agent_workbench.core.config import LLMConfig
from tests.langchain_doubles import make_scripted_chat_model


def _answer(text: str) -> Any:
    return make_scripted_chat_model(lambda _n: AIMessage(content=text), "fake")


def _thread(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def _ask(graph: Any, text: str, thread_id: str = "t1") -> Any:
    return await graph.ainvoke({"messages": [HumanMessage(text)]}, _thread(thread_id))


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


async def test_restart_keeps_the_conversation(tmp_path: Path) -> None:
    path = tmp_path / "c.sqlite"
    saver = await agent.open_checkpointer(path)
    try:
        await _ask(agent.build_graph(_answer("answer 1"), [], saver), "question 1")
    finally:
        await saver.conn.close()

    seen: list[list[BaseMessage]] = []
    model = _answer("answer 2")
    scripted = type(model)._agenerate

    async def capturing(
        self: Any, messages: list[BaseMessage], *a: Any, **k: Any
    ) -> Any:
        seen.append(list(messages))
        return await scripted(self, messages, *a, **k)

    saver = await agent.open_checkpointer(path)
    try:
        graph = agent.build_graph(model, [], saver)
        state = await graph.aget_state(_thread("t1"))
        assert [m.content for m in state.values["messages"]] == [
            "question 1",
            "answer 1",
        ]
        with patch.object(type(model), "_agenerate", capturing):
            await _ask(graph, "question 2")
    finally:
        await saver.conn.close()

    assert [[m.content for m in messages] for messages in seen] == [
        ["question 1", "answer 1", "question 2"]
    ]


async def test_secure_delete_is_on(tmp_path: Path) -> None:
    saver = await agent.open_checkpointer(tmp_path / "c.sqlite")
    try:
        async with saver.conn.execute("PRAGMA secure_delete") as cursor:
            row = await cursor.fetchone()
    finally:
        await saver.conn.close()
    assert row is not None
    assert row[0] == 1


async def test_delete_on_a_fresh_database(tmp_path: Path) -> None:
    saver = await agent.open_checkpointer(tmp_path / "c.sqlite")
    try:
        await saver.adelete_thread("never-used")
    finally:
        await saver.conn.close()


async def test_delete_and_wal_checkpoint_remove_the_thread(tmp_path: Path) -> None:
    saver = await agent.open_checkpointer(tmp_path / "c.sqlite")
    try:
        await _ask(agent.build_graph(_answer("hi"), [], saver), "hello")
        assert await saver.aget_tuple(_thread("t1")) is not None
        await saver.adelete_thread("t1")
        await agent.checkpoint_wal(saver)
        assert await saver.aget_tuple(_thread("t1")) is None
    finally:
        await saver.conn.close()


async def test_wal_checkpoint_failure_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    saver = await agent.open_checkpointer(tmp_path / "c.sqlite")
    try:
        with (
            patch.object(
                saver.conn, "execute", side_effect=sqlite3.OperationalError("boom")
            ),
            caplog.at_level(logging.ERROR, logger=agent.__name__),
        ):
            await agent.checkpoint_wal(saver)
    finally:
        await saver.conn.close()
    assert "boom" in caplog.text
    assert not saver.lock.locked()


@pytest.mark.usefixtures("fresh_runtime")
async def test_concurrent_first_calls_build_once() -> None:
    llm_config = LLMConfig(backend="openai", model="gpt-4o")
    model = _answer("hi")
    with (
        patch.object(agent, "load_llm_config", return_value=llm_config),
        patch.object(agent, "create_chat_model", return_value=model) as create,
    ):
        try:
            first, second = await asyncio.gather(
                agent.get_runtime(), agent.get_runtime()
            )
        finally:
            await agent.close_runtime()

    assert second is first
    assert first.checkpointer is not None
    create.assert_called_once()
    assert agent._runtime is None


@pytest.mark.usefixtures("fresh_runtime")
async def test_runtime_uses_the_sessions_folder(app_data: Path) -> None:
    with (
        patch.object(agent, "load_llm_config"),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
    ):
        try:
            await agent.get_runtime()
        finally:
            await agent.close_runtime()
    assert (app_data / "sessions" / "checkpoints.sqlite").is_file()


@pytest.mark.usefixtures("fresh_runtime")
async def test_failure_after_open_closes_the_connection() -> None:
    opened: list[Any] = []
    open_checkpointer = agent.open_checkpointer

    async def spy(path: Path) -> Any:
        opened.append(await open_checkpointer(path))
        return opened[-1]

    with (
        patch.object(agent, "load_llm_config"),
        patch.object(agent, "create_chat_model", return_value=_answer("hi")),
        patch.object(agent, "open_checkpointer", side_effect=spy),
        patch.object(agent, "build_graph", side_effect=RuntimeError("no graph")),
        pytest.raises(RuntimeError, match="no graph"),
    ):
        await agent.get_runtime()

    assert len(opened) == 1
    saver = opened[0]
    with pytest.raises(ValueError, match="no active connection"):
        await saver.conn.execute("SELECT 1")
    assert agent._runtime is None


@pytest.mark.usefixtures("fresh_runtime")
async def test_close_runtime_without_runtime() -> None:
    await agent.close_runtime()
    assert agent._runtime is None


def test_sessions_dir_is_created_in_app_data(app_data: Path) -> None:
    path = agent.sessions_dir()
    assert path == app_data / "sessions"
    assert path.is_dir()
