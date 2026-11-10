"""Chainlit data layer on SQLite: schema and the ``SessionDataLayer`` subclass.

Chainlit is imported here and in ``ui_handlers`` only; only ``ui_handlers`` imports this
module.
"""

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from sqlalchemy import URL, event

logger = logging.getLogger(__name__)

_TABLES = ("users", "threads", "steps", "elements", "feedbacks")

# Adapted from the Chainlit SQLAlchemy docs: TEXT for UUID / JSONB / TEXT[], plus the
# Chainlit 2.12.0 columns the docs lack. Chainlit deletes child rows itself, so no
# foreign keys (SQLite ignores ON DELETE CASCADE without PRAGMA foreign_keys anyway).
_DDL = """
CREATE TABLE IF NOT EXISTS users (
    "id" TEXT PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" TEXT NOT NULL,
    "createdAt" TEXT
);
CREATE TABLE IF NOT EXISTS threads (
    "id" TEXT PRIMARY KEY,
    "createdAt" TEXT,
    "name" TEXT,
    "userId" TEXT,
    "userIdentifier" TEXT,
    "tags" TEXT,
    "metadata" TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    "id" TEXT PRIMARY KEY,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "threadId" TEXT NOT NULL,
    "parentId" TEXT,
    "command" TEXT,
    "modes" TEXT,
    "streaming" BOOLEAN NOT NULL,
    "waitForAnswer" BOOLEAN,
    "isError" BOOLEAN,
    "metadata" TEXT,
    "tags" TEXT,
    "input" TEXT,
    "output" TEXT,
    "createdAt" TEXT,
    "start" TEXT,
    "end" TEXT,
    "generation" TEXT,
    "showInput" TEXT,
    "defaultOpen" BOOLEAN,
    "autoCollapse" BOOLEAN,
    "language" TEXT,
    "icon" TEXT
);
CREATE TABLE IF NOT EXISTS elements (
    "id" TEXT PRIMARY KEY,
    "threadId" TEXT,
    "type" TEXT,
    "chainlitKey" TEXT,
    "path" TEXT,
    "url" TEXT,
    "objectKey" TEXT,
    "name" TEXT NOT NULL,
    "display" TEXT,
    "size" TEXT,
    "language" TEXT,
    "page" INTEGER,
    "props" TEXT,
    "autoPlay" BOOLEAN,
    "playerConfig" TEXT,
    "forId" TEXT,
    "mime" TEXT
);
CREATE TABLE IF NOT EXISTS feedbacks (
    "id" TEXT PRIMARY KEY,
    "forId" TEXT NOT NULL,
    "threadId" TEXT,
    "value" INTEGER NOT NULL,
    "comment" TEXT
);
"""


def expected_columns() -> dict[str, list[str]]:
    """Return the columns of each table as defined by our DDL."""
    with closing(sqlite3.connect(":memory:")) as mem:
        mem.executescript(_DDL)
        return _columns(mem)


def prepare_database(path: Path) -> None:
    """Create missing tables in *path*, set WAL mode and log missing columns.

    ``CREATE TABLE IF NOT EXISTS`` never adds columns to an existing table; a missing
    column is logged as an error, not migrated.

    Args:
        path: The Chainlit database file, created if missing.
    """
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(_DDL)
        # Persistent in the file: Chainlit writes over a pool from background tasks.
        conn.execute("PRAGMA journal_mode=WAL")
        have = _columns(conn)
    for table, columns in expected_columns().items():
        for column in columns:
            if column not in have[table]:
                logger.error(
                    "chainlit.sqlite: column %s.%s missing – created by an older"
                    " version; its data is not saved",
                    table,
                    column,
                )


def _columns(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Return the column names of each of our tables (``PRAGMA table_info``)."""
    return {
        table: [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
        for table in _TABLES
    }


class SessionDataLayer(SQLAlchemyDataLayer):  # type: ignore[misc]  # chainlit skipped by mypy
    """Chainlit's SQLAlchemy data layer on our SQLite file, with SQLite fixes.

    SQLite has no array or JSON type: tags are JSON-encoded on write, and the JSON
    columns are decoded when threads are read.
    """

    def __init__(self, db_path: Path) -> None:
        prepare_database(db_path)
        # URL.create, not an f-string: survives Windows paths and "%" / "#".
        url = URL.create("sqlite+aiosqlite", database=str(db_path))
        super().__init__(conninfo=url)
        event.listen(self.engine.sync_engine, "connect", _set_secure_delete)

    async def update_thread(
        self,
        thread_id: str,
        name: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Save the thread; *tags* JSON-encoded (``None`` leaves the column alone)."""
        await super().update_thread(
            thread_id,
            name=name,
            user_id=user_id,
            metadata=metadata,
            tags=_encode_tags(tags),
        )

    async def create_step(self, step_dict: dict[str, Any]) -> None:
        """Save a copy of the step with JSON-encoded tags; *step_dict* is untouched."""
        step = dict(step_dict)
        if "tags" in step:
            step["tags"] = _encode_tags(step["tags"])
        await super().create_step(step)

    async def get_all_user_threads(
        self, user_id: str | None = None, thread_id: str | None = None
    ) -> list[dict[str, Any]] | None:
        """Return Chainlit's threads with the JSON columns decoded."""
        threads: list[dict[str, Any]] | None = await super().get_all_user_threads(
            user_id=user_id, thread_id=thread_id
        )
        for thread in threads or []:
            for key in ("tags", "metadata"):
                thread[key] = _decode_json(thread.get(key))
            for step in thread.get("steps") or []:
                for key in ("tags", "metadata", "generation"):
                    step[key] = _decode_json(step.get(key))
        return threads


def _encode_tags(tags: Any) -> Any:
    """Return a list of tags as a JSON string, anything else unchanged."""
    return json.dumps(tags) if isinstance(tags, list) else tags


def _decode_json(value: Any) -> Any:
    """Return a JSON string decoded (``"null"`` → None), anything else unchanged."""
    return json.loads(value) if isinstance(value, str) else value


def _set_secure_delete(dbapi_conn: Any, _record: Any) -> None:
    """Turn on ``secure_delete`` for each new connection of the engine's pool."""
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA secure_delete=ON")
    finally:
        cursor.close()
