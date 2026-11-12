"""Fixtures shared by all test folders."""

import logging
import shutil
from collections.abc import Iterator

import pytest

# Chainlit creates these in the working directory when imported without CHAINLIT_APP_ROOT.
_CHAINLIT_DIRS = (".chainlit", ".files")


def pytest_configure(config: pytest.Config) -> None:
    """Remove Chainlit folders left in the repo root before the run, with a warning.

    The suite's own Chainlit import never writes there (``tests/apps/conftest.py``,
    checked by ``test_repo_root_untouched_by_chainlit_import``). Folders present before
    the run come from an import outside it, e.g. ``get_library_source`` on a Chainlit
    module (mcp-tools-py #288).
    """
    for name in _CHAINLIT_DIRS:
        path = config.rootpath / name
        if path.is_dir():
            shutil.rmtree(path)
            config.issue_config_time_warning(
                pytest.PytestWarning(
                    f"Removed {path}: left by a Chainlit import outside the test run"
                ),
                stacklevel=2,
            )


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
