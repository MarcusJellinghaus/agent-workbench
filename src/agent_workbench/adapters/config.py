"""Config file reader and ``[llm]`` loader.

Precedence per key: ``AGENT_WORKBENCH_LLM_*`` env var (empty = unset), then
``~/.agent_workbench/config.toml`` ``[llm]``, then unset.
"""

import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp_coder_utils.user_app_data import get_user_app_data_dir

from agent_workbench.adapters.toml_utils import format_toml_error
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
    """

    path: Path
    exists: bool
    parse_error: str | None
    llm: dict[str, Any]


def config_file_path() -> Path:
    """Return the user config file path.

    Returns:
        ``~/.agent_workbench/config.toml``.
    """
    return get_user_app_data_dir("agent_workbench") / "config.toml"


def read_config_file(path: Path | None = None) -> ConfigFile:
    """Read the config file and extract its raw ``[llm]`` table.

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
    llm = data.get("llm", {})
    if not isinstance(llm, dict):
        return ConfigFile(
            path, True, f"[llm] must be a table, got {type(llm).__name__}", {}
        )
    return ConfigFile(path, True, None, llm)


def wrong_type_keys(llm: Mapping[str, Any]) -> list[str]:
    """Return the known keys whose value is not a string.

    Args:
        llm: Raw ``[llm]`` table.

    Returns:
        Offending keys in ``LLM_KEYS`` order.
    """
    return [key for key in LLM_KEYS if key in llm and not isinstance(llm[key], str)]


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
    bad_keys = wrong_type_keys(config_file.llm)
    if bad_keys:
        logger.warning(
            "Ignoring config file %s: [llm] %s must be strings; see the CONFIG "
            "section of `agent-workbench verify`.",
            config_file.path,
            ", ".join(bad_keys),
        )
        return LLMConfig()
    env = {key: os.environ.get(var) or None for key, var in ENV_VARS.items()}
    return LLMConfig(
        **{key: env.get(key) or config_file.llm.get(key) for key in LLM_KEYS}
    )
