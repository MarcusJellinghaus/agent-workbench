"""Chainlit data layer on SQLite: schema and (step 3) the SessionDataLayer subclass."""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

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
