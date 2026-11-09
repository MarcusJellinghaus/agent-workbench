"""``verify`` checks: config, LLM provider and a live test prompt.

Returns a structured :class:`VerifyReport`; printing is left to ``interfaces``.
The copied model layer is imported inside :func:`run_verify` so that importing
this module stays light (no ``langchain_core`` at import time).
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_workbench.adapters import config as adapters_config
from agent_workbench.adapters import llm
from agent_workbench.adapters.config_hints import unknown_key_hint
from agent_workbench.core.config import LLM_KEYS, LLMConfig

logger = logging.getLogger(__name__)

TEST_PROMPT = "Reply with OK"
TEST_PROMPT_TIMEOUT = 30

_LLM_LABEL = "[llm]"


@dataclass
class VerifyReport:
    """Result of all ``verify`` checks.

    Attributes:
        config_path: The config file path.
        config_entries: CONFIG rows, each ``{"label", "status", "value"}`` with
            status ``"ok"`` | ``"warning"`` | ``"error"`` | ``"info"``.
        config_has_error: Whether the CONFIG section found an error.
        backend: Configured backend, or None.
        provider: ``check_provider()`` rows incl. ``effective_config`` and
            ``overall_ok``.
        test_prompt_error: None when the test prompt answered; else the
            failure category text.
        install_hints: Install hints of failed provider rows.
        exit_code: 0 when every exit-relevant check passed, else 1.
    """

    config_path: Path
    config_entries: list[dict[str, str]]
    config_has_error: bool
    backend: str | None
    provider: dict[str, Any]
    test_prompt_error: str | None
    install_hints: list[str]
    exit_code: int


def _llm_entry(status: str, value: str) -> dict[str, str]:
    return {"label": _LLM_LABEL, "status": status, "value": value}


def verify_config(
    config_file: adapters_config.ConfigFile,
) -> tuple[list[dict[str, str]], bool]:
    """Check the config file and its ``[llm]`` section.

    Args:
        config_file: The read config file.

    Returns:
        Tuple of the CONFIG rows and whether any of them is an error.
    """
    entries: list[dict[str, str]] = []
    path = config_file.path
    if not config_file.exists:
        entries.append(
            {"label": "Config file", "status": "warning", "value": "not found"}
        )
        entries.append({"label": "Expected path", "status": "info", "value": str(path)})
        entries.append(
            {
                "label": "Hint",
                "status": "info",
                "value": "See the Configuration section of the README to create it",
            }
        )
    elif config_file.parse_error:
        entries.append(
            {"label": "Config file", "status": "error", "value": "invalid TOML"}
        )
        entries.append(
            {
                "label": "Parse error",
                "status": "error",
                "value": config_file.parse_error,
            }
        )
        return entries, True
    else:
        entries.append({"label": "Config file", "status": "ok", "value": str(path)})

    env = {key: os.environ.get(var) for key, var in adapters_config.ENV_VARS.items()}
    section = config_file.llm
    if not section:
        # Section absent: report env vars, but don't list every unset key.
        env_rows = [
            _llm_entry("ok", f"{key} configured (env var)")
            for key in LLM_KEYS
            if env.get(key)
        ]
        entries.extend(env_rows or [_llm_entry("info", "not configured")])
        return entries, False

    has_error = False
    for key in LLM_KEYS:
        config_value = section.get(key)
        if env.get(key):
            source = (
                "(env var, also in config.toml)"
                if config_value is not None
                else "(env var)"
            )
            entries.append(_llm_entry("ok", f"{key} configured {source}"))
        elif config_value is not None:
            if not isinstance(config_value, str):
                entries.append(
                    _llm_entry(
                        "error",
                        f"{key}: expected str, got {type(config_value).__name__} "
                        f"('{config_value}')",
                    )
                )
                has_error = True
            else:
                entries.append(_llm_entry("ok", f"{key} configured (config.toml)"))
        else:
            entries.append(_llm_entry("info", f"{key} not configured"))

    for key in section:
        if key not in LLM_KEYS:
            hint = unknown_key_hint("llm", key, LLM_KEYS)
            entries.append(
                _llm_entry(
                    "warning", f"unknown key: {key}" + (f" — {hint}" if hint else "")
                )
            )

    return entries, has_error


def collect_install_hints(rows: dict[str, Any]) -> list[str]:
    """Collect ``install_hint`` values from failed provider rows.

    Args:
        rows: ``check_provider()`` result.

    Returns:
        Install hints of every failed row that carries one.
    """
    return [
        entry["install_hint"]
        for entry in rows.values()
        if isinstance(entry, dict) and not entry.get("ok") and "install_hint" in entry
    ]


def compute_exit_code(
    config_has_error: bool, overall_ok: bool, test_prompt_ok: bool
) -> int:
    """Compute the ``verify`` exit code.

    Advisory rows (``available_models``, ``model_check``) are not consulted.

    Args:
        config_has_error: Whether the CONFIG section found an error.
        overall_ok: ``check_provider()``'s ``overall_ok``.
        test_prompt_ok: Whether the test prompt answered.

    Returns:
        1 if any of the three failed, else 0.
    """
    if config_has_error or not overall_ok or not test_prompt_ok:
        return 1
    return 0


def _run_test_prompt(config: LLMConfig) -> str | None:
    """Send the test prompt.

    Args:
        config: The loaded LLM configuration.

    Returns:
        None when the prompt answered, else the failure category text.
    """
    from agent_workbench.adapters.langchain._exceptions import (
        classify_connection_error,
        format_diagnostics,
    )

    try:
        llm.invoke(
            llm.create_chat_model(config, TEST_PROMPT_TIMEOUT), config, TEST_PROMPT
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Only classify connection-related exceptions
        if isinstance(exc, (OSError, ConnectionError)):
            category = classify_connection_error(exc)
            logger.debug("Connection diagnostics:\n%s", format_diagnostics(exc))
        else:
            category = f"{type(exc).__name__}: {exc}"
        logger.debug("Test prompt failure details: %s", exc, exc_info=True)
        return category
    return None


def run_verify(check_models: bool = False) -> VerifyReport:
    """Run every ``verify`` check.

    Args:
        check_models: If True, also list the backend's models (advisory only).

    Returns:
        The structured report.
    """
    from agent_workbench.adapters.langchain import _provider_checks

    config_file = adapters_config.read_config_file()
    entries, config_has_error = verify_config(config_file)
    config = adapters_config.load_llm_config(config_file)
    rows = _provider_checks.check_provider(config.as_dict(), check_models=check_models)
    test_prompt_error = _run_test_prompt(config)
    return VerifyReport(
        config_path=config_file.path,
        config_entries=entries,
        config_has_error=config_has_error,
        backend=config.backend,
        provider=rows,
        test_prompt_error=test_prompt_error,
        install_hints=collect_install_hints(rows),
        exit_code=compute_exit_code(
            config_has_error, bool(rows["overall_ok"]), test_prompt_error is None
        ),
    )
