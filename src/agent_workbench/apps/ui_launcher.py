"""Launcher of the Chainlit chat page (``agent-workbench-ui``).

Chainlit reads its environment once, at its first import, so this module must not import
Chainlit at module level: ``prepare_chainlit_env`` has to run first.
"""

import json
import logging
import os
from importlib.metadata import version
from pathlib import Path

from agent_workbench.apps.origin_check import local_origins

logger = logging.getLogger(__name__)

CHAINLIT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# Env vars that would switch on a Chainlit feature this app does not configure (data
# layer, chat platforms, custom auth, root path, TLS), plus the ChainlitConfig fields
# that pydantic-settings fills from env vars of the same name (case-insensitive).
_REMOVED_ENV_VARS: tuple[str, ...] = (
    "DATABASE_URL",
    "LITERAL_API_KEY",
    "DISCORD_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_WEBSOCKET_TOKEN",
    "SLACK_SIGNING_SECRET",
    "TEAMS_APP_ID",
    "TEAMS_APP_PASSWORD",
    "CHAINLIT_CUSTOM_AUTH",
    "CHAINLIT_ROOT_PATH",
    "CHAINLIT_PARENT_ROOT_PATH",
    "CHAINLIT_SSL_CERT",
    "CHAINLIT_SSL_KEY",
    "ROOT",
    "CHAINLIT_SERVER",
    "RUN",
)

# Chainlit merges nothing into this file: keys left out take the model defaults.
# edit_message is off: an edit re-runs the handler outside the task that Stop cancels,
# and the page and the LangGraph thread would get out of step.
_CONFIG_TEMPLATE = """\
[project]
allow_origins = {origins}

[features]
edit_message = false

[features.spontaneous_file_upload]
enabled = false

[features.mcp]
enabled = false

[UI]
name = "agent-workbench"

[meta]
generated_by = "{version}"
"""


def chainlit_port() -> int:
    """Return the port of the chat page: ``CHAINLIT_PORT`` or ``DEFAULT_PORT``."""
    return int(os.environ.get("CHAINLIT_PORT") or DEFAULT_PORT)


def prepare_chainlit_env(app_data: Path) -> Path:
    """Set up the environment Chainlit reads at its first import.

    Points Chainlit's app root and ``.env`` file into the app-data folder, removes the
    env vars in ``_REMOVED_ENV_VARS`` (warning per var that was set) and forces the
    host to ``CHAINLIT_HOST``.

    Args:
        app_data: The user app-data folder.

    Returns:
        The Chainlit app root, ``<app_data>/chainlit``.
    """
    root = app_data / "chainlit"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["CHAINLIT_APP_ROOT"] = str(root)
    # Never created: Chainlit must not load a .env file from the working directory.
    os.environ["CHAINLIT_ENV_FILE"] = str(root / "no-env-file.env")
    removed = set(_REMOVED_ENV_VARS)
    for var in [name for name in os.environ if name.upper() in removed]:
        del os.environ[var]
        logger.warning("Ignoring %s: not supported by agent-workbench-ui", var)
    host = os.environ.get("CHAINLIT_HOST")
    if host and host != CHAINLIT_HOST:
        logger.warning(
            "Ignoring CHAINLIT_HOST=%s: the chat page listens on %s only",
            host,
            CHAINLIT_HOST,
        )
    os.environ["CHAINLIT_HOST"] = CHAINLIT_HOST
    return root


def write_chainlit_config(app_root: Path, port: int) -> Path:
    """Write Chainlit's ``config.toml`` from the fixed template.

    Args:
        app_root: The Chainlit app root.
        port: The port of the chat page, for the allowed origins.

    Returns:
        The path of the written file.
    """
    config_dir = app_root / ".chainlit"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "config.toml"
    path.write_text(
        _CONFIG_TEMPLATE.format(
            origins=json.dumps(local_origins(port)), version=version("chainlit")
        ),
        encoding="utf-8",
    )
    return path
