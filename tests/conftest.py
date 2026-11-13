"""Fixtures shared by all test folders."""

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture
def restore_root_logging() -> Iterator[None]:
    """Restore the root logger's handlers and level; close every handler added.

    For tests calling the real ``setup_logging``: Windows cannot delete an open log file.
    """
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    for handler in root.handlers[:]:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    for handler in handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(level)
