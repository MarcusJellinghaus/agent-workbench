"""Tests for the ``[permissions]`` parser and resolver."""

import tomllib
from typing import Any

import pytest

from agent_workbench.core.permissions import PermissionMode
from agent_workbench.services.permissions import (
    LABEL,
    PermissionConfig,
    parse_permissions,
)

# tool name -> group, as built from the configured specs
TOOLS: dict[str, str] = {
    "list_tables": "sql.schema",
    "validate_sql": "sql.validate",
    "verify": "sql.validate",
    "read_file": "workspace.read",
    "save_file": "workspace.write",
}


@pytest.mark.parametrize(
    ("entries", "tool", "group", "expected"),
    [
        pytest.param(
            {"validate_sql": "allow", "sql.validate": "deny"},
            "validate_sql",
            "sql.validate",
            ("allow", "tool"),
            id="tool-beats-group",
        ),
        pytest.param(
            {"validate_sql": "allow", "sql.validate": "ask"},
            "verify",
            "sql.validate",
            ("ask", "group"),
            id="group-applies",
        ),
        pytest.param(
            {"sql.schema": "allow"},
            "read_file",
            "workspace.read",
            ("deny", "unlisted"),
            id="unlisted-deny",
        ),
    ],
)
def test_mode_of(
    entries: dict[str, PermissionMode],
    tool: str,
    group: str,
    expected: tuple[PermissionMode, str],
) -> None:
    assert PermissionConfig(entries).mode_of(tool, group) == expected


def test_mode_of_default_config_denies() -> None:
    assert PermissionConfig().mode_of("read_file", "workspace.read") == (
        "deny",
        "unlisted",
    )


def test_valid_entries() -> None:
    table = {
        "sql.schema": "allow",
        "validate_sql": "ask",
        "workspace.read": "ask_session",
        "workspace.write": "deny",
    }
    config, rows = parse_permissions(table, None, TOOLS)
    assert config.entries == table
    assert rows == []


def test_type_error_single_row_and_empty_config() -> None:
    config, rows = parse_permissions({}, "expected table, got str", TOOLS)
    assert config == PermissionConfig()
    assert rows == [(LABEL, "error", "expected table, got str")]


def test_empty_table_warning() -> None:
    config, rows = parse_permissions({}, None, TOOLS)
    assert config.entries == {}
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "warning")
    assert "every tool is deny" in message


@pytest.mark.parametrize("value", ["yes", "Allow", 1, True, ["allow"]])
def test_unknown_mode_error(value: Any) -> None:
    config, rows = parse_permissions({"validate_sql": value}, None, TOOLS)
    assert "validate_sql" not in config.entries
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "error")
    assert message.startswith("validate_sql ")
    assert "unknown mode" in message
    assert "allow, ask, ask_session, deny" in message


def test_unquoted_dotted_key_error() -> None:
    config, rows = parse_permissions({"sql": {"schema": "allow"}}, None, TOOLS)
    assert config.entries == {}
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "error")
    assert message.startswith("sql ")
    assert "quote group names" in message
    assert '"sql.schema"' in message


def test_unquoted_dotted_key_lists_every_sub_key() -> None:
    _config, rows = parse_permissions(
        {"workspace": {"read": "allow", "write": "ask"}}, None, TOOLS
    )
    assert len(rows) == 1
    message = rows[0][2]
    assert '"workspace.read"' in message
    assert '"workspace.write"' in message


def test_three_level_dotted_key_suggests_the_full_path() -> None:
    table = tomllib.loads('[permissions]\na.b.c = "allow"\n')["permissions"]
    config, rows = parse_permissions(table, None, TOOLS)
    assert config.entries == {}
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "error")
    assert message.startswith("a ")
    assert '"a.b.c" = ...' in message
    assert '"a.b" = ...' not in message


def test_quoted_key_with_inline_table_is_not_called_unquoted() -> None:
    table = tomllib.loads('[permissions]\n"x" = { y = "allow" }\n')["permissions"]
    config, rows = parse_permissions(table, None, TOOLS)
    assert config.entries == {}
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "error")
    assert message.startswith("x ")
    assert "nested table, not a mode" in message
    assert "unquoted" not in message


def test_empty_inline_table_is_an_error_without_suggestion() -> None:
    _config, rows = parse_permissions({"x": {}}, None, TOOLS)
    assert rows == [(LABEL, "error", "x is a table, not a mode")]


def test_key_both_tool_and_group_error() -> None:
    tools = {**TOOLS, "sql.schema": "other"}
    config, rows = parse_permissions({"sql.schema": "allow"}, None, tools)
    assert "sql.schema" not in config.entries
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "error")
    assert message.startswith("sql.schema ")
    assert "both a tool name and a group name" in message


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("no_such_tool", id="unknown-tool"),
        pytest.param("sql.update", id="unknown-group"),
    ],
)
def test_unknown_key_warning(key: str) -> None:
    config, rows = parse_permissions({key: "ask"}, None, TOOLS)
    assert len(rows) == 1
    label, status, message = rows[0]
    assert (label, status) == (LABEL, "warning")
    assert message.startswith(f"{key} ")
    assert "has no effect" in message
    assert key not in config.entries


def test_valid_and_invalid_entries_mixed() -> None:
    table = {
        "sql.schema": "allow",
        "validate_sql": "maybe",
        "sql": {"validate": "allow"},
        "workspace.read": "ask_session",
    }
    config, rows = parse_permissions(table, None, TOOLS)
    assert config.entries == {"sql.schema": "allow", "workspace.read": "ask_session"}
    assert [status for _label, status, _message in rows] == ["error", "error"]
