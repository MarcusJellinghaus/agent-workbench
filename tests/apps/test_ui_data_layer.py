"""SessionDataLayer: round trip, tags and JSON fixes, secure_delete."""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from chainlit.context import init_http_context
from chainlit.types import Feedback
from chainlit.user import User

from agent_workbench.apps import ui_data_layer
from agent_workbench.apps.ui_data_layer import SessionDataLayer


def _step(thread_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": "user",
        "type": "user_message",
        "threadId": thread_id,
        "streaming": False,
        "output": "hello",
        "createdAt": "2026-01-01T00:00:00Z",
        **extra,
    }


def _raw(db_path: Path, query: str, *params: str) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(query, params).fetchall()


async def test_round_trip_decodes_json(data_layer: SessionDataLayer) -> None:
    user = await data_layer.create_user(User(identifier="alice"))
    assert user is not None
    thread_id = str(uuid.uuid4())
    await data_layer.update_thread(
        thread_id, name="Chat", user_id=user.id, metadata={"k": "v"}
    )
    init_http_context()
    await data_layer.create_step(
        _step(thread_id, metadata={"m": 1}, generation={"g": [1]})
    )

    threads = await data_layer.get_all_user_threads(user_id=user.id)

    assert threads is not None
    [thread] = threads
    assert thread["id"] == thread_id
    assert thread["name"] == "Chat"
    assert thread["metadata"] == {"k": "v"}
    [step] = thread["steps"]
    assert step["output"] == "hello"
    assert step["metadata"] == {"m": 1}
    assert step["generation"] == {"g": [1]}


async def test_thread_tags_round_trip(data_layer: SessionDataLayer) -> None:
    thread_id = str(uuid.uuid4())
    await data_layer.update_thread(thread_id, name="Chat", tags=["a"])

    thread = await data_layer.get_thread(thread_id)

    assert thread is not None
    assert thread["tags"] == ["a"]


async def test_thread_without_tags_stores_null(
    data_layer: SessionDataLayer, tmp_path: Path
) -> None:
    thread_id = str(uuid.uuid4())
    await data_layer.update_thread(thread_id, name="one")
    await data_layer.update_thread(thread_id, name="two")

    rows = _raw(
        tmp_path / "chainlit.sqlite",
        'SELECT "tags" FROM threads WHERE id = ?',
        thread_id,
    )

    assert rows == [(None,)]


async def test_step_tags_round_trip_leave_caller_dict(
    data_layer: SessionDataLayer,
) -> None:
    thread_id = str(uuid.uuid4())
    step = _step(thread_id, tags=["t"])
    init_http_context()

    await data_layer.create_step(step)

    assert step["tags"] == ["t"]
    assert "showInput" not in step
    thread = await data_layer.get_thread(thread_id)
    assert thread is not None
    [saved] = thread["steps"]
    assert saved["tags"] == ["t"]


async def test_feedback_without_thread_id_is_saved(
    data_layer: SessionDataLayer, tmp_path: Path
) -> None:
    step_id = str(uuid.uuid4())

    feedback_id = await data_layer.upsert_feedback(Feedback(forId=step_id, value=1))

    rows = _raw(
        tmp_path / "chainlit.sqlite",
        'SELECT "forId", "value" FROM feedbacks WHERE id = ?',
        feedback_id,
    )
    assert rows == [(step_id, 1)]


async def test_engine_connections_use_secure_delete(
    data_layer: SessionDataLayer,
) -> None:
    async with data_layer.engine.connect() as conn:
        result = await conn.exec_driver_sql("PRAGMA secure_delete")
        assert result.scalar() == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('["a"]', ["a"]),
        ("null", None),
        ({"a": 1}, {"a": 1}),
        (["a"], ["a"]),
        (None, None),
    ],
)
def test_decode_json(value: Any, expected: Any) -> None:
    assert ui_data_layer._decode_json(value) == expected
