"""Config file reader, ``[llm]`` loader and ``[tools]`` validation.

Precedence per ``[llm]`` key: ``AGENT_WORKBENCH_LLM_*`` env var (empty = unset), then
``~/.agent_workbench/config.toml`` ``[llm]``, then unset. ``[tools.*]`` tables have
no env vars; :func:`tools_config_problems` checks their shape; their keys belong to the
toolset provider of the same name.
"""

import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_workbench.adapters.toml_utils import format_toml_error
from agent_workbench.adapters.user_app_data import get_user_app_data_dir
from agent_workbench.core.config import LLM_KEYS, LLMConfig

logger = logging.getLogger(__name__)

# No app env var for api_key: the vendor env var beats config inside the copied backends.
ENV_VARS: dict[str, str] = {
    "backend": "AGENT_WORKBENCH_LLM_BACKEND",
    "model": "AGENT_WORKBENCH_LLM_MODEL",
    "base_url": "AGENT_WORKBENCH_LLM_BASE_URL",
    "api_version": "AGENT_WORKBENCH_LLM_API_VERSION",
}


@dataclass(frozen=True)
class ConfigFile:
    """Result of reading the config file.

    Attributes:
        path: The config file path.
        exists: Whether the file exists.
        parse_error: Formatted TOML / read error, or None.
        llm: Raw ``[llm]`` table; empty when absent or unreadable.
        llm_type_error: Set when ``[llm]`` is present but not a table.
        tools: Raw ``[tools]`` table; empty when absent or unreadable.
        tools_type_error: Set when ``[tools]`` is present but not a table.
    """

    path: Path
    exists: bool
    parse_error: str | None
    llm: dict[str, Any]
    llm_type_error: str | None = None
    tools: dict[str, Any] = field(default_factory=dict)
    tools_type_error: str | None = None


def app_data_dir() -> Path:
    """Return the user app-data folder.

    Returns:
        ``~/.agent_workbench``.
    """
    return get_user_app_data_dir("agent_workbench")


def config_file_path() -> Path:
    """Return the user config file path.

    Returns:
        ``~/.agent_workbench/config.toml``.
    """
    return app_data_dir() / "config.toml"


def _table(data: Mapping[str, Any], name: str) -> tuple[dict[str, Any], str | None]:
    """Return the top-level table *name* and its type error.

    Args:
        data: The parsed TOML document.
        name: Top-level key.

    Returns:
        The table (empty when absent or not a table) and the type error or None.
    """
    value = data.get(name, {})
    if not isinstance(value, dict):
        return {}, f"expected table, got {type(value).__name__}"
    return value, None


def read_config_file(path: Path | None = None) -> ConfigFile:
    """Read the config file and extract its raw ``[llm]`` and ``[tools]`` tables.

    Args:
        path: Config file to read; defaults to ``config_file_path()``.

    Returns:
        The read result. Never raises for missing or invalid files.
    """
    path = path or config_file_path()
    if not path.exists():
        return ConfigFile(path, False, None, {})
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return ConfigFile(path, True, format_toml_error(path, e), {})
    except OSError as e:
        return ConfigFile(path, True, f"Error reading config file: {path}\n{e}", {})
    llm, llm_type_error = _table(data, "llm")
    tools, tools_type_error = _table(data, "tools")
    return ConfigFile(
        path,
        True,
        None,
        llm,
        llm_type_error,
        tools=tools,
        tools_type_error=tools_type_error,
    )


def env_values() -> dict[str, str | None]:
    """Return the ``AGENT_WORKBENCH_LLM_*`` overrides; an empty value counts as unset.

    Returns:
        Mapping of each key in ``ENV_VARS`` to its env value or None.
    """
    return {key: os.environ.get(var) or None for key, var in ENV_VARS.items()}


def wrong_type_keys(llm: Mapping[str, Any]) -> list[str]:
    """Return the known keys whose config value is not a string.

    A key overridden by its env var is not checked: the env value wins, as in
    mcp_coder's ``get_config_values``.

    Args:
        llm: Raw ``[llm]`` table.

    Returns:
        Offending keys in ``LLM_KEYS`` order.
    """
    env = env_values()
    return [
        key
        for key in LLM_KEYS
        if key in llm and not env.get(key) and not isinstance(llm[key], str)
    ]


def tools_config_problems(config_file: ConfigFile) -> list[tuple[str, str, str]]:
    """Return ``(label, status, message)`` error rows for the shape of ``[tools]``.

    Only the shape is checked: ``[tools]`` and each ``[tools.<name>]`` must be tables.
    Keys and paths belong to the provider registered as ``<name>`` (its ``verify`` rows).

    Args:
        config_file: The read config file.

    Returns:
        Problem rows; empty when ``[tools]`` is valid or absent.
    """
    if config_file.tools_type_error:
        return [("[tools]", "error", config_file.tools_type_error)]
    return [
        (f"[tools.{name}]", "error", f"expected table, got {type(table).__name__}")
        for name, table in config_file.tools.items()
        if not isinstance(table, dict)
    ]


def load_llm_config(config_file: ConfigFile | None = None) -> LLMConfig:
    """Load the effective LLM config. Never raises.

    Args:
        config_file: Already-read config file; read from disk when None.

    Returns:
        The merged config; all keys unset when the file is invalid.
    """
    config_file = config_file or read_config_file()
    if config_file.parse_error:
        logger.warning(
            "Ignoring invalid config file %s; see the CONFIG section of "
            "`agent-workbench verify`.",
            config_file.path,
        )
        return LLMConfig()
    if config_file.llm_type_error:
        logger.warning(
            "Ignoring config file %s: [llm] %s; see the CONFIG section of "
            "`agent-workbench verify`.",
            config_file.path,
            config_file.llm_type_error,
        )
        return LLMConfig()
    bad_keys = wrong_type_keys(config_file.llm)
    if bad_keys:
        logger.warning(
            "Ignoring config file %s: [llm] %s must be strings; see the CONFIG "
            "section of `agent-workbench verify`.",
            config_file.path,
            ", ".join(bad_keys),
        )
        return LLMConfig()
    env = env_values()
    return LLMConfig(
        **{key: env.get(key) or config_file.llm.get(key) for key in LLM_KEYS}
    )
