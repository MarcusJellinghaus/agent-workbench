"""``verify`` checks: config, tools, LLM provider and a live test prompt.

Returns a structured :class:`VerifyReport`; printing is left to ``interfaces``.
The copied model layer is imported inside :func:`run_verify` so that importing
this module stays light (no ``langchain_core`` at import time).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_workbench.adapters import config as adapters_config
from agent_workbench.adapters import llm, toolset_providers
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
        tools_entries: TOOLS rows, same shape as ``config_entries``.
        tools_has_error: Whether the TOOLS section found an error.
    """

    config_path: Path
    config_entries: list[dict[str, str]]
    config_has_error: bool
    backend: str | None
    provider: dict[str, Any]
    test_prompt_error: str | None
    install_hints: list[str]
    exit_code: int
    tools_entries: list[dict[str, str]] = field(default_factory=list)
    tools_has_error: bool = False


def _llm_entry(status: str, value: str) -> dict[str, str]:
    return {"label": _LLM_LABEL, "status": status, "value": value}


def _row(label: str, status: str, value: str) -> dict[str, str]:
    return {"label": label, "status": status, "value": value}


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
        if config_file.llm_type_error:
            entries.append(_llm_entry("error", config_file.llm_type_error))
            return entries, True

    env = adapters_config.env_values()
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


def verify_tools(
    config_file: adapters_config.ConfigFile, *, connect: bool
) -> tuple[list[dict[str, str]], bool]:
    """Check ``[tools]``: shape, provider registered, then the provider's own ``verify`` rows.

    No tool-specific checks: rows come from ``ToolsetProvider.verify(connect=connect)``.

    Args:
        config_file: The read config file.
        connect: Passed to each provider's ``verify``; True may open connections.

    Returns:
        TOOLS rows (``{"label", "status", "value"}``) and whether any is an error.
    """
    if config_file.parse_error:
        return [_row("[tools]", "info", "not checked – invalid config file")], False
    if not config_file.tools and not config_file.tools_type_error:
        return [_row("[tools]", "info", "not configured")], False
    rows = [
        _row(label, status, message)
        for label, status, message in adapters_config.tools_config_problems(config_file)
    ]
    for name, table in config_file.tools.items():
        if not isinstance(table, dict):
            continue
        label = f"[tools.{name}]"
        try:
            cls = toolset_providers.provider_class(name)
        except ValueError as exc:
            rows.append(_row(label, "error", str(exc)))
            continue
        try:
            items = cls(table).verify(connect=connect)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # The provider contract says verify doesn't raise; report it if it does.
            rows.append(
                _row(label, "error", f"verify failed: {type(exc).__name__}: {exc}")
            )
            continue
        rows.extend(
            _row(
                label,
                item.status,
                f"{item.name}: {item.message}"
                + (f" – {item.hint}" if item.hint else ""),
            )
            for item in items
        )
    return rows, any(row["status"] == "error" for row in rows)


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
    config_has_error: bool,
    overall_ok: bool,
    test_prompt_ok: bool,
    tools_has_error: bool = False,
) -> int:
    """Compute the ``verify`` exit code.

    Advisory rows (``available_models``, ``model_check``) are not consulted.

    Args:
        config_has_error: Whether the CONFIG section found an error.
        overall_ok: ``check_provider()``'s ``overall_ok``.
        test_prompt_ok: Whether the test prompt answered.
        tools_has_error: Whether the TOOLS section found an error.

    Returns:
        1 if any of the four failed, else 0.
    """
    if config_has_error or not overall_ok or not test_prompt_ok or tools_has_error:
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


def run_verify(
    check_models: bool = False, *, connect_tools: bool = True
) -> VerifyReport:
    """Run every ``verify`` check.

    Args:
        check_models: If True, also list the backend's models (advisory only).
        connect_tools: Passed to the toolset providers' ``verify`` as ``connect``;
            False opens no tool connection.

    Returns:
        The structured report.
    """
    from agent_workbench.adapters.langchain import _provider_checks

    config_file = adapters_config.read_config_file()
    entries, config_has_error = verify_config(config_file)
    tools_entries, tools_has_error = verify_tools(config_file, connect=connect_tools)
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
            config_has_error,
            bool(rows["overall_ok"]),
            test_prompt_error is None,
            tools_has_error,
        ),
        tools_entries=tools_entries,
        tools_has_error=tools_has_error,
    )
