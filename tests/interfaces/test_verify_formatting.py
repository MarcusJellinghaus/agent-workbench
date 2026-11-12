from pathlib import Path
from typing import Any

from agent_workbench.interfaces.verify_formatting import (
    format_config_section,
    format_report,
    format_row,
    format_section,
    pad,
)
from agent_workbench.services.verify import VerifyReport


def _report(**overrides: Any) -> VerifyReport:
    fields: dict[str, Any] = {
        "config_path": Path("config.toml"),
        "config_entries": [],
        "config_has_error": False,
        "backend": "openai",
        "provider": {"overall_ok": True},
        "test_prompt_error": None,
        "install_hints": [],
        "exit_code": 0,
    }
    fields.update(overrides)
    return VerifyReport(**fields)


def _line(text: str, needle: str) -> str:
    return next(line for line in text.splitlines() if needle in line)


def test_pad_is_75_chars() -> None:
    header = pad("CONFIG")
    assert header.startswith("\n=== CONFIG ")
    assert len(header.lstrip("\n")) == 75


def test_format_row_strips_trailing_space() -> None:
    row = format_row("Label", "", "", indent=2)
    assert row == "  Label"


def test_format_section_symbols_and_labels() -> None:
    text = format_section(
        "DETAILS",
        {
            "backend": {"ok": True, "value": "openai"},
            "backend_package": {"ok": False, "value": "missing", "error": "boom"},
            "base_url_shape": {"ok": None, "value": "odd"},
            "overall_ok": False,
        },
    )
    assert "[OK]" in _line(text, "Backend ")
    assert "openai" in _line(text, "Backend ")
    assert "[ERR]" in _line(text, "Backend package")
    assert "missing (boom)" in _line(text, "Backend package")
    assert "[WARN]" in _line(text, "Base URL")
    assert "overall_ok" not in text


def test_format_section_skips_effective_config_list() -> None:
    text = format_section(
        "DETAILS",
        {"effective_config": [("Model", "gpt-4o")], "overall_ok": True},
    )
    assert "gpt-4o" not in text
    assert "effective_config" not in text


def test_format_section_install_hint_line() -> None:
    text = format_section(
        "DETAILS",
        {
            "backend_package": {
                "ok": False,
                "value": "not installed",
                "install_hint": "pip install langchain-openai",
            }
        },
    )
    lines = text.splitlines()
    index = lines.index(_line(text, "Backend package"))
    assert lines[index + 1].strip() == "-> pip install langchain-openai"


def test_format_config_section_groups_llm() -> None:
    text = format_config_section(
        [
            {"label": "Config file", "status": "ok", "value": "/x/config.toml"},
            {"label": "[llm]", "status": "ok", "value": "backend configured (env var)"},
            {"label": "[llm]", "status": "info", "value": "model not configured"},
        ]
    )
    lines = text.splitlines()
    assert "[OK]" in lines[0] and "Config file" in lines[0]
    assert lines[1] == "  [llm]"
    assert lines[2].startswith("    backend")
    assert "[OK]" in lines[2]
    assert "configured (env var)" in lines[2]
    assert lines[3].startswith("    model")
    assert "[" not in lines[3]


def test_format_report_sections_in_order() -> None:
    text = format_report(
        _report(
            provider={
                "effective_config": [("Model", "gpt-4o (from config.toml)")],
                "backend": {"ok": True, "value": "openai"},
                "overall_ok": True,
            }
        )
    )
    order = [
        "=== CONFIG",
        "=== LLM PROVIDER ",
        "=== EFFECTIVE CONFIG",
        "=== LLM PROVIDER DETAILS",
        "Test prompt",
    ]
    positions = [text.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert "openai" in _line(text, "Active provider")
    assert "gpt-4o (from config.toml)" in _line(text, "Model")
    assert "responded OK" in _line(text, "Test prompt")
    assert "INSTALL INSTRUCTIONS" not in text


def test_format_report_tools_section_after_config() -> None:
    text = format_report(
        _report(
            config_entries=[{"label": "[llm]", "status": "ok", "value": "x"}],
            tools_entries=[
                {"label": "[tools.fake]", "status": "ok", "value": "config.a: found"},
                {"label": "[tools.fake]", "status": "error", "value": "config.b: bad"},
                {
                    "label": "[tools.fake]",
                    "status": "warning",
                    "value": "config.c: odd",
                },
            ],
            tools_has_error=True,
        )
    )
    lines = text.splitlines()
    assert text.index("=== CONFIG") < text.index("=== TOOLS")
    assert text.index("=== TOOLS") < text.index("=== LLM PROVIDER ")
    header = lines.index("  [tools.fake]")
    assert lines.index(next(x for x in lines if x.startswith("=== TOOLS"))) < header
    assert "[OK]" in lines[header + 1] and "config.a: found" in lines[header + 1]
    assert "[ERR]" in lines[header + 2] and "config.b: bad" in lines[header + 2]
    assert "[WARN]" in lines[header + 3] and "config.c: odd" in lines[header + 3]


def test_format_report_not_configured() -> None:
    text = format_report(_report(backend=None))
    assert "not configured" in _line(text, "Active provider")
    assert "EFFECTIVE CONFIG" not in text


def test_format_report_test_prompt_failure() -> None:
    text = format_report(_report(test_prompt_error="Connection refused"))
    row = _line(text, "Test prompt")
    assert "[ERR]" in row
    assert "FAILED (Connection refused)" in row
    assert "--log-level DEBUG" in text


def test_format_report_install_instructions_joined() -> None:
    text = format_report(
        _report(
            install_hints=[
                "pip install langchain-openai",
                "pip install langchain-core",
                "set OPENAI_API_KEY",
            ]
        )
    )
    assert "=== INSTALL INSTRUCTIONS" in text
    assert "  pip install langchain-openai langchain-core" in text.splitlines()
