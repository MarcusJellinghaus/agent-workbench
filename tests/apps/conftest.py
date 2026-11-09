"""Isolate Chainlit before any test module imports it.

Chainlit reads ``CHAINLIT_APP_ROOT`` and ``CHAINLIT_ENV_FILE`` once, at its first import,
and creates ``.files/`` and ``.chainlit/`` in that root (the working directory by
default). A fixture runs too late: pytest imports the test modules, and with them
Chainlit, during collection. Module-level code in this conftest runs in every xdist
worker before the test modules of this folder are imported.
"""

import tempfile
from pathlib import Path

from agent_workbench.apps.ui_launcher import prepare_chainlit_env

prepare_chainlit_env(Path(tempfile.mkdtemp(prefix="aw-chainlit-")))
