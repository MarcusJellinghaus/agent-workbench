"""SessionDataLayer delete: both databases, deleted set, finish_turn, WAL checkpoints."""

import logging
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from chainlit.context import init_http_context
from chainlit.types import Feedback
from chainlit.user import User
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_workbench.apps import agent, ui_data_layer
from agent_workbench.apps.ui_data_layer import SessionDataLayer
from tests.langchain_doubles import make_scripted_chat_model


def _step(thread_id: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": "user",
        "type": "user_message",
        "threadId": thread_id,
        "streaming": False,
        "output": "hello",
        "createdAt": "2026-01-01T00:00:00Z",
    }


_COUNT = {
    "threads": 'SELECT COUNT(*) FROM threads WHERE "id" = ?',
    "steps": 'SELECT COUNT(*) FROM steps WHERE "threadId" = ?',
    "feedbacks": 'SELECT COUNT(*) FROM feedbacks WHERE "forId" = ?',
}


def _count(db_path: Path, table: str, value: str) -> int:
    """Count the rows of *table* for *value* (thread id; step id for feedbacks)."""
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(_COUNT[table], (value,)).fetchone()
    return int(row[0])


def _thread(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def _turn(saver: AsyncSqliteSaver, thread_id: str) -> None:
    """Write checkpoints for *thread_id* with one graph turn of the scripted model."""
    model = make_scripted_chat_model(lambda _n: AIMessage(content="hi"), "fake")
    graph = agent.build_graph(model, [], saver)
    await graph.ainvoke({"messages": [HumanMessage("hello")]}, _thread(thread_id))
    assert await saver.aget_tuple(_thread(thread_id)) is not None


async def _user_thread(data_layer: SessionDataLayer) -> tuple[str, str]:
    """Create a user and a thread of that user; return (user id, thread id)."""
    user = await data_layer.create_user(User(identifier="alice"))
    assert user is not None
    thread_id = str(uuid.uuid4())
    await data_layer.update_thread(thread_id, name="Chat", user_id=user.id)
    return user.id, thread_id


async def test_delete_removes_both_databases(
    data_layer: SessionDataLayer, checkpointer: AsyncSqliteSaver, tmp_path: Path
) -> None:
    db = tmp_path / "chainlit.sqlite"
    _, thread_id = await _user_thread(data_layer)
    init_http_context()
    step = _step(thread_id)
    await data_layer.create_step(step)
    await data_layer.upsert_feedback(
        Feedback(forId=step["id"], value=1, threadId=thread_id)
    )
    await _turn(checkpointer, thread_id)
    assert _count(db, "feedbacks", step["id"]) == 1

    await data_layer.delete_thread(thread_id)

    assert _count(db, "threads", thread_id) == 0
    assert _count(db, "steps", thread_id) == 0
    assert _count(db, "feedbacks", step["id"]) == 0
    assert await checkpointer.aget_tuple(_thread(thread_id)) is None
    for wal in (tmp_path / "chainlit.sqlite-wal", tmp_path / "checkpoints.sqlite-wal"):
        assert not wal.exists() or wal.stat().st_size == 0


async def test_delete_on_a_fresh_checkpointer_database(
    data_layer: SessionDataLayer, tmp_path: Path
) -> None:
    _, thread_id = await _user_thread(data_layer)

    await data_layer.delete_thread(thread_id)

    assert _count(tmp_path / "chainlit.sqlite", "threads", thread_id) == 0


async def test_failing_checkpointer_delete_keeps_the_thread(
    data_layer: SessionDataLayer, checkpointer: AsyncSqliteSaver
) -> None:
    user_id, thread_id = await _user_thread(data_layer)

    with (
        patch.object(
            checkpointer, "adelete_thread", side_effect=sqlite3.OperationalError("boom")
        ),
        pytest.raises(sqlite3.OperationalError, match="boom"),
    ):
        await data_layer.delete_thread(thread_id)

    threads = await data_layer.get_all_user_threads(user_id=user_id)
    assert [thread["id"] for thread in threads or []] == [thread_id]
    assert thread_id not in data_layer._deleted


async def test_no_writes_after_delete(
    data_layer: SessionDataLayer, tmp_path: Path
) -> None:
    db = tmp_path / "chainlit.sqlite"
    _, thread_id = await _user_thread(data_layer)
    await data_layer.delete_thread(thread_id)

    await data_layer.update_thread(thread_id, name="again")
    init_http_context()
    await data_layer.create_step(_step(thread_id))

    assert _count(db, "threads", thread_id) == 0
    assert _count(db, "steps", thread_id) == 0


async def test_finish_turn_deletes_late_checkpoints(
    data_layer: SessionDataLayer, checkpointer: AsyncSqliteSaver
) -> None:
    _, thread_id = await _user_thread(data_layer)
    await data_layer.delete_thread(thread_id)
    await _turn(checkpointer, thread_id)

    await data_layer.finish_turn(thread_id)

    assert await checkpointer.aget_tuple(_thread(thread_id)) is None


async def test_finish_turn_keeps_a_live_thread(
    data_layer: SessionDataLayer, checkpointer: AsyncSqliteSaver, tmp_path: Path
) -> None:
    _, thread_id = await _user_thread(data_layer)
    await _turn(checkpointer, thread_id)

    await data_layer.finish_turn(thread_id)

    assert _count(tmp_path / "chainlit.sqlite", "threads", thread_id) == 1
    assert await checkpointer.aget_tuple(_thread(thread_id)) is not None


async def test_wal_checkpoint_failure_is_logged(
    data_layer: SessionDataLayer, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        # On the class: AsyncEngine has __slots__.
        patch.object(
            type(data_layer.engine),
            "connect",
            side_effect=sqlite3.OperationalError("boom"),
        ),
        caplog.at_level(logging.ERROR, logger=ui_data_layer.__name__),
    ):
        await data_layer._checkpoint_wal()

    assert "boom" in caplog.text
