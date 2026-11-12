"""Isolate Chainlit before any test module imports it.

Chainlit reads ``CHAINLIT_APP_ROOT`` and ``CHAINLIT_ENV_FILE`` once, at its first import,
and creates ``.files/`` and ``.chainlit/`` in that root (the working directory by
default). A fixture runs too late: pytest imports the test modules, and with them
Chainlit, during collection. Module-level code in this conftest runs in every xdist
worker before the test modules of this folder are imported.

The repo root's ``.chainlit/`` and ``.files/`` are recorded first, so
``test_repo_root_untouched_by_chainlit_import`` can check that the import left them as
they were. Nothing is deleted: they may hold a developer's own files.
"""

import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from agent_workbench.apps.ui_launcher import prepare_chainlit_env

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from agent_workbench.apps.ui_data_layer import SessionDataLayer

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAINLIT_DEFAULT_DIRS = (".chainlit", ".files")

FolderSnapshot = dict[str, tuple[int, int] | None]


def snapshot_chainlit_dirs() -> dict[str, FolderSnapshot | None]:
    """Return each Chainlit default folder in the repo root, or None when absent.

    Returns:
        Per folder name: every entry's relative path mapped to the file's size and
        mtime (None for a directory).
    """
    snapshot: dict[str, FolderSnapshot | None] = {}
    for name in CHAINLIT_DEFAULT_DIRS:
        folder = REPO_ROOT / name
        if not folder.is_dir():
            snapshot[name] = None
            continue
        entries: FolderSnapshot = {}
        for entry in folder.rglob("*"):
            stat = entry.stat()
            entries[entry.relative_to(folder).as_posix()] = (
                (stat.st_size, stat.st_mtime_ns) if entry.is_file() else None
            )
        snapshot[name] = entries
    return snapshot


# Before the first Chainlit import.
_CHAINLIT_DIRS_BEFORE_IMPORT = snapshot_chainlit_dirs()

prepare_chainlit_env(Path(tempfile.mkdtemp(prefix="aw-chainlit-")))


@pytest.fixture
def chainlit_dirs_before_and_now() -> tuple[
    dict[str, FolderSnapshot | None], dict[str, FolderSnapshot | None]
]:
    """The repo root's Chainlit default folders before Chainlit's import, and now."""
    import chainlit.config  # noqa: F401  # pylint: disable=unused-import

    return _CHAINLIT_DIRS_BEFORE_IMPORT, snapshot_chainlit_dirs()


@pytest.fixture(autouse=True)
def _chainlit_data_layer() -> Iterator[None]:
    """No data layer unless a test installs one; Chainlit's globals restored after."""
    import chainlit.data

    saved = chainlit.data._data_layer, chainlit.data._data_layer_initialized
    chainlit.data._data_layer = None
    chainlit.data._data_layer_initialized = True
    yield
    chainlit.data._data_layer, chainlit.data._data_layer_initialized = saved


@pytest.fixture
async def checkpointer(tmp_path: Path) -> AsyncIterator["AsyncSqliteSaver"]:
    """A real SQLite checkpointer on ``tmp_path``; its connection closed after."""
    from agent_workbench.apps import agent

    saver = await agent.open_checkpointer(tmp_path / "checkpoints.sqlite")
    yield saver
    await saver.conn.close()


@pytest.fixture
async def data_layer(
    tmp_path: Path, checkpointer: "AsyncSqliteSaver"
) -> AsyncIterator["SessionDataLayer"]:
    """A ``SessionDataLayer`` on ``tmp_path``, installed as Chainlit's data layer."""
    import chainlit.data

    from agent_workbench.apps.ui_data_layer import SessionDataLayer

    layer = SessionDataLayer(
        tmp_path / "chainlit.sqlite", AsyncMock(return_value=checkpointer)
    )
    chainlit.data._data_layer = layer
    yield layer
    await layer.close()
