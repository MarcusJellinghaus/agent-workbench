"""Formatting of the ``verify`` report for the terminal.

The LangChain subset of mcp_coder's ``cli/commands/verify_formatting.py`` and
the printing in its ``verify.py``. Depends only on the standard library and
:class:`~agent_workbench.services.verify.VerifyReport`.
"""

import keyword
import re
from typing import Any

from agent_workbench.services.verify import VerifyReport

STATUS_SYMBOLS: dict[str, str] = {
    "success": "[OK]",
    "failure": "[ERR]",
    "warning": "[WARN]",
}

_MARKER_SLOT_WIDTH: int = max(len(v) for v in STATUS_SYMBOLS.values())
_LABEL_WIDTH: int = 22

_CONFIG_STATUS_SYMBOLS: dict[str, str] = {
    "ok": STATUS_SYMBOLS["success"],
    "warning": STATUS_SYMBOLS["warning"],
    "error": STATUS_SYMBOLS["failure"],
}

_LABEL_MAP: dict[str, str] = {
    "backend": "Backend",
    "model": "Model",
    "api_key": "API key",
    "api_version": "API version",
    "langchain_core": "LangChain core",
    "backend_package": "Backend package",
    # "base_url" (contract finding) and "base_url_shape" (heuristic) share a
    # label but are mutually exclusive by construction.
    "base_url": "Base URL",
    "base_url_shape": "Base URL",
    "base_url_redirect": "Base URL redirect",
    "api_key_override": "API key override",
    "available_models": "Available models",
    "model_check": "Model available",
    "ollama_daemon": "Local Ollama daemon",
    "ollama_tools_capability": "Tool-calling capability",
}

_KEY_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _format_row_prefix(label: str, marker: str, *, indent: int) -> str:
    """Render the column-aligned prefix of a row.

    Returns:
        ``indent + label_field + " " + marker_field + " "``, trailing space kept.
    """
    return f"{' ' * indent}{label:<{_LABEL_WIDTH}s} {marker:<{_MARKER_SLOT_WIDTH}s} "


_VALUE_COLUMN_INDENT: int = len(_format_row_prefix("", "", indent=2))


def format_row(label: str, marker: str, value: str, *, indent: int) -> str:
    """Render a tabular row (labeled or label-less).

    Args:
        label: Row label (may be empty).
        marker: Status marker (e.g. ``[OK]``, or "").
        value: Row value text.
        indent: Number of leading spaces.

    Returns:
        Formatted row with trailing whitespace stripped.
    """
    return (_format_row_prefix(label, marker, indent=indent) + value).rstrip()


def pad(title: str) -> str:
    r"""Return a section header line padded to 75 chars with '='."""
    prefix = f"=== {title} "
    return "\n" + prefix + "=" * max(0, 75 - len(prefix))


def _looks_like_key(token: str) -> bool:
    """Return True if *token* is a non-keyword Python identifier."""
    return bool(_KEY_REGEX.match(token)) and not keyword.iskeyword(token)


def format_section(title: str, rows: dict[str, Any]) -> str:
    """Format a section of check rows.

    Args:
        title: Section title.
        rows: Check rows keyed by check name; ``overall_ok`` and non-dict
            entries are skipped.

    Returns:
        Formatted multi-line section.
    """
    lines: list[str] = [pad(title)]
    for key, entry in rows.items():
        if key == "overall_ok" or not isinstance(entry, dict):
            continue
        ok = entry.get("ok")
        if ok is True:
            symbol = STATUS_SYMBOLS["success"]
        elif ok is False:
            symbol = STATUS_SYMBOLS["failure"]
        else:
            symbol = STATUS_SYMBOLS["warning"]
        value = str(entry.get("value", ""))
        error = entry.get("error")
        if error and ok is False:
            value = f"{value} ({error})"
        lines.append(format_row(_LABEL_MAP.get(key, key), symbol, value, indent=2))
        if ok is False and "install_hint" in entry:
            lines.append(f"{' ' * _VALUE_COLUMN_INDENT}-> {entry['install_hint']}")
    return "\n".join(lines)


def format_config_section(entries: list[dict[str, str]]) -> str:
    """Format the CONFIG rows, grouping ``[section]`` rows under a header.

    Args:
        entries: CONFIG rows, each ``{"label", "status", "value"}``.

    Returns:
        Formatted rows (without the section header).
    """
    lines: list[str] = []
    last_label: str | None = None
    for entry in entries:
        label = entry["label"]
        symbol = _CONFIG_STATUS_SYMBOLS.get(entry["status"], "")
        value = entry["value"]
        if label.startswith("["):
            if label != last_label:
                if last_label is not None:
                    lines.append("")  # blank line between groups
                lines.append(f"  {label}")
                last_label = label
            first, _sep, rest = value.partition(" ")
            if _looks_like_key(first) and rest:
                lines.append(format_row(first, symbol, rest, indent=4))
            else:
                lines.append(format_row("", symbol, value, indent=4))
        else:
            # Top-level rows (Config file, Expected path, Hint, Parse error)
            lines.append(format_row(label, symbol, value, indent=2))
    return "\n".join(lines)


def format_report(report: VerifyReport) -> str:
    """Format the full ``verify`` report.

    Args:
        report: The structured verify result.

    Returns:
        The report text, sections in mcp_coder's order.
    """
    parts: list[str] = [
        pad("CONFIG"),
        format_row("Config path", "", str(report.config_path), indent=2),
        format_config_section(report.config_entries),
        pad("TOOLS"),
        format_config_section(report.tools_entries),
        pad("LLM PROVIDER"),
        format_row(
            "Active provider",
            STATUS_SYMBOLS["success"] if report.backend else STATUS_SYMBOLS["warning"],
            report.backend or "not configured",
            indent=2,
        ),
    ]
    effective_config = report.provider.get("effective_config")
    if effective_config:
        parts.append(pad("EFFECTIVE CONFIG"))
        parts.extend(
            format_row(label, "", value, indent=2) for label, value in effective_config
        )
    parts.append(format_section("LLM PROVIDER DETAILS", report.provider))
    if report.test_prompt_error is None:
        parts.append(
            format_row(
                "Test prompt", STATUS_SYMBOLS["success"], "responded OK", indent=2
            )
        )
    else:
        parts.append(
            format_row(
                "Test prompt",
                STATUS_SYMBOLS["failure"],
                f"FAILED ({report.test_prompt_error})",
                indent=2,
            )
        )
        parts.append("  Run with --log-level DEBUG for detailed diagnostics.")
    pip_packages = " ".join(
        hint.replace("pip install ", "")
        for hint in report.install_hints
        if hint.startswith("pip install")
    )
    if pip_packages:
        parts.append(pad("INSTALL INSTRUCTIONS"))
        parts.append(f"  pip install {pip_packages}")
    return "\n".join(parts)
