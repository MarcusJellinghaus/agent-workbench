"""Tests for the permission mode type."""

from typing import get_args

from agent_workbench.core.permissions import PERMISSION_MODES, PermissionMode


def test_permission_modes_in_order() -> None:
    assert PERMISSION_MODES == ("allow", "ask", "ask_session", "deny")


def test_permission_modes_match_literal() -> None:
    assert get_args(PermissionMode) == PERMISSION_MODES
