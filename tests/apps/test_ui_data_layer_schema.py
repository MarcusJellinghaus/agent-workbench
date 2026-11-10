"""The SQLite schema for Chainlit's data layer: coverage, creation, missing columns."""

import dataclasses
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from chainlit.element import ElementDict
from chainlit.step import StepDict
from chainlit.types import Feedback, ThreadDict

from agent_workbench.apps import ui_data_layer

_TABLES = {"users", "threads", "steps", "elements", "feedbacks"}


def _missing(keys: set[str], table: str) -> set[str]:
    return keys - set(ui_data_layer.expected_columns()[table])


def test_threads_cover_thread_dict() -> None:
    keys = set(ThreadDict.__annotations__) - {"steps", "elements"}
    assert not _missing(keys, "threads")


def test_steps_cover_step_dict() -> None:
    keys = set(StepDict.__annotations__) - {"feedback"}
    assert not _missing(keys, "steps")


def test_elements_cover_element_dict() -> None:
    assert not _missing(set(ElementDict.__annotations__), "elements")


def test_feedbacks_cover_feedback() -> None:
    keys = {field.name for field in dataclasses.fields(Feedback)}
    assert not _missing(keys, "feedbacks")


def test_prepare_database_creates_tables_in_wal_mode(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "c.sqlite"
    with caplog.at_level(logging.ERROR, logger=ui_data_layer.__name__):
        ui_data_layer.prepare_database(path)
        ui_data_layer.prepare_database(path)

    with closing(sqlite3.connect(path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert tables >= _TABLES
    assert mode == "wal"
    assert not caplog.records


def test_missing_column_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "c.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('CREATE TABLE steps ("id" TEXT PRIMARY KEY, "name" TEXT)')
        conn.commit()

    with caplog.at_level(logging.ERROR, logger=ui_data_layer.__name__):
        ui_data_layer.prepare_database(path)

    assert "steps.icon" in caplog.text
    assert "threads." not in caplog.text
