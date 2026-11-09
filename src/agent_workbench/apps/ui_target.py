"""Chainlit target: imports the handler module (absolute imports only).

``run_chainlit`` loads this file by path, without its parent package, and puts its
folder on ``sys.path``.
"""

import agent_workbench.apps.ui_handlers  # noqa: F401  # pylint: disable=unused-import
