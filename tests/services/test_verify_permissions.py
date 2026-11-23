"""PERMISSIONS section of ``verify``: ``verify_permissions`` and its exit-code effect."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agent_workbench.adapters.config import read_config_file
from agent_workbench.services.verify import run_verify, verify_permissions
from tests.adapters.tool_fixtures import (
    FakeProvider,
    new_provider,
    register_providers,
    write_config_file,
)

_LABEL = "[permissions]"
_NO_ENTRIES = {
    "label": _LABEL,
    "status": "warning",
    "value": "no entries – every tool is deny",
}


def _row(status: str, value: str) -> dict[str, str]:
    return {"label": _LABEL, "status": status, "value": value}


def _write(
    tmp_path: Path, tools: dict[str, dict[str, Any]], permissions: str = ""
) -> Path:
    """Write ``[tools.<name>]`` tables, with *permissions* text placed before them."""
    path = write_config_file(tmp_path, tools)
    path.write_text(
        permissions + "\n" + path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return path


def _check(
    path: Path, *, tools_has_error: bool = False
) -> tuple[list[dict[str, str]], bool]:
    rows, has_error = verify_permissions(
        read_config_file(path), tools_has_error=tools_has_error
    )
    assert has_error == any(row["status"] == "error" for row in rows)
    return rows, has_error


@pytest.fixture(name="provider")
def _provider(monkeypatch: pytest.MonkeyPatch) -> type[FakeProvider]:
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    return provider


# --- problem rows -----------------------------------------------------------


@pytest.mark.usefixtures("provider")
def test_unknown_tool_and_group_are_warnings(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"fake": {}},
        '[permissions]\nnope = "allow"\n"no.group" = "ask"\necho = "allow"\n',
    )
    rows, has_error = _check(path)
    assert not has_error
    warnings = [row["value"] for row in rows if row["status"] == "warning"]
    assert len(warnings) == 2
    assert warnings[0].startswith("nope names no tool or group")
    assert warnings[1].startswith("no.group names no tool or group")


@pytest.mark.usefixtures("provider")
@pytest.mark.parametrize(
    ("permissions", "needle"),
    [
        ('[permissions]\necho = "sometimes"\n', "echo has an unknown mode 'sometimes'"),
        ('[permissions]\nfake.read = "allow"\n', "quote group names"),
        ('permissions = "x"\n', "expected table, got str"),
    ],
)
def test_errors(tmp_path: Path, permissions: str, needle: str) -> None:
    rows, has_error = _check(_write(tmp_path, {"fake": {}}, permissions))
    assert has_error
    errors = [row for row in rows if row["status"] == "error"]
    assert len(errors) == 1
    assert errors[0]["label"] == _LABEL
    assert needle in errors[0]["value"]


@pytest.mark.usefixtures("provider")
def test_key_both_tool_and_group_is_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"fake": {"tools": ["shell"], "group": "shell"}},
        '[permissions]\nshell = "allow"\n',
    )
    rows, has_error = _check(path)
    assert has_error
    assert _row("error", "shell is both a tool name and a group name") in rows


@pytest.mark.usefixtures("provider")
@pytest.mark.parametrize("permissions", ["", "[permissions]\n"])
def test_no_entries_warning(tmp_path: Path, permissions: str) -> None:
    rows, has_error = _check(_write(tmp_path, {"fake": {}}, permissions))
    assert not has_error
    assert rows == [_NO_ENTRIES, _row("info", "echo deny (unlisted)")]


# --- not checked ------------------------------------------------------------


def test_no_tools_not_checked(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[permissions]\necho = "allow"\n', encoding="utf-8")
    with patch(
        "agent_workbench.adapters.toolset_providers.build_toolsets"
    ) as build_toolsets:
        rows, has_error = _check(path)
    assert rows == [_row("info", "not checked – no [tools]")]
    assert not has_error
    build_toolsets.assert_not_called()


def test_invalid_toml_not_checked(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[permissions\n", encoding="utf-8")
    rows, has_error = _check(path)
    assert rows == [_row("info", "not checked – invalid config file")]
    assert not has_error


# --- build ------------------------------------------------------------------


@pytest.mark.usefixtures("provider")
def test_build_failure_is_error(tmp_path: Path) -> None:
    rows, has_error = _check(_write(tmp_path, {"fake": {"fail": "boom"}}))
    assert has_error
    assert rows == [
        _row(
            "error",
            "building the tools failed: ValueError: [tools.fake] fake build failed: boom",
        )
    ]


@pytest.mark.usefixtures("provider")
def test_build_failure_with_tools_error_not_checked(tmp_path: Path) -> None:
    path = _write(tmp_path, {"fake": {"fail": "boom"}})
    rows, has_error = _check(path, tools_has_error=True)
    assert rows == [_row("info", "not checked – fix the TOOLS errors first")]
    assert not has_error


@pytest.mark.usefixtures("provider")
def test_build_succeeds_despite_tools_error(tmp_path: Path) -> None:
    path = _write(tmp_path, {"fake": {}}, '[permissions]\necho = "ask"\n')
    rows, has_error = _check(path, tools_has_error=True)
    assert rows == [_row("info", "echo ask (tool)")]
    assert not has_error


def test_effective_mode_and_source_per_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, other = new_provider(), new_provider()
    register_providers(monkeypatch, {"fake": fake, "other": other})
    path = _write(
        tmp_path,
        {
            "fake": {"tools": ["echo", "write"]},
            "other": {"tools": ["lone"], "group": "other.grp"},
        },
        '[permissions]\n"fake.read" = "ask"\nwrite = "allow"\nnope = "sometimes"\n',
    )
    rows, has_error = _check(path)
    assert has_error
    assert [row["value"] for row in rows if row["status"] == "info"] == [
        "echo ask (group fake.read)",
        "write allow (tool)",
        "lone deny (unlisted)",
    ]
    assert [toolset.closed for toolset in (*fake.built, *other.built)] == [True, True]


# --- run_verify -------------------------------------------------------------


def test_run_verify_permissions_error_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: type[FakeProvider]
) -> None:
    path = _write(tmp_path, {"fake": {}}, '[permissions]\necho = "sometimes"\n')
    monkeypatch.setattr(
        "agent_workbench.adapters.config.config_file_path", lambda: path
    )
    with (
        patch(
            "agent_workbench.adapters.langchain._provider_checks.check_provider",
            return_value={"overall_ok": True},
        ),
        patch("agent_workbench.services.verify._run_test_prompt", return_value=None),
    ):
        report = run_verify()
    assert not report.config_has_error
    assert not report.tools_has_error
    assert report.permissions_has_error
    assert _row("info", "echo deny (unlisted)") in report.permissions_entries
    assert report.exit_code == 1
    assert [toolset.closed for toolset in provider.built] == [True]
