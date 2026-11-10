"""Isolate Chainlit before any test module imports it.

Chainlit reads ``CHAINLIT_APP_ROOT`` and ``CHAINLIT_ENV_FILE`` once, at its first import,
and creates ``.files/`` and ``.chainlit/`` in that root (the working directory by
default). A fixture runs too late: pytest imports the test modules, and with them
Chainlit, during collection. Module-level code in this conftest runs in every xdist
worker before the test modules of this folder are imported.
"""

import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_workbench.apps.ui_launcher import prepare_chainlit_env

if TYPE_CHECKING:
    from agent_workbench.apps.ui_data_layer import SessionDataLayer

prepare_chainlit_env(Path(tempfile.mkdtemp(prefix="aw-chainlit-")))


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
async def data_layer(tmp_path: Path) -> AsyncIterator["SessionDataLayer"]:
    """A ``SessionDataLayer`` on ``tmp_path``, installed as Chainlit's data layer."""
    import chainlit.data

    from agent_workbench.apps.ui_data_layer import SessionDataLayer

    layer = SessionDataLayer(tmp_path / "chainlit.sqlite")
    chainlit.data._data_layer = layer
    yield layer
    await layer.close()
