import pytest

from agent_workspace.core.greeting import greet


def test_greet_default() -> None:
    assert greet() == "Hello, world!"


def test_greet_name() -> None:
    assert greet("Marcus") == "Hello, Marcus!"


@pytest.mark.parametrize("name", ["", "   "])
def test_greet_blank_falls_back_to_world(name: str) -> None:
    assert greet(name) == "Hello, world!"
