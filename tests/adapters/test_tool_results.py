"""Tests for result_text: the text the model receives for a tool result."""

from pathlib import Path
from typing import Any

import pytest

from agent_workbench.adapters.tool_results import result_text


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("x", "x"),
        ({"a": 1}, '{"a": 1}'),
        (["a", "b"], '["a", "b"]'),
        ([], "[]"),
        (True, "true"),
        (None, "null"),
        ({"name": "Größe"}, '{"name": "Größe"}'),
        ({"path": Path("a")}, '{"path": "a"}'),
    ],
)
def test_result_text(result: Any, expected: str) -> None:
    """A string passes through; anything else becomes JSON with non-ASCII kept."""
    assert result_text(result) == expected
