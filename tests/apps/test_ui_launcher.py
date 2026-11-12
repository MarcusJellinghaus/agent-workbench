"""``main`` of ``agent-workbench-ui``: dependency check, ``verify``, toolset build, Chainlit start."""

import importlib.util
import os
import re
from collections.abc import Iterator
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent_workbench.apps import ui_launcher
from agent_workbench.services.logging_setup import setup_logging as real_setup_logging
from tests.adapters.tool_fixtures import (
    new_provider,
    register_providers,
    write_config_file,
)

ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - the value the launcher must refuse
_real_find_spec = importlib.util.find_spec


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path) -> Iterator[MagicMock]:
    """Patch app data, logging, truststore and Chainlit; yield the ``_run_chainlit`` mock."""
    with (
        patch.dict(os.environ),
        patch("agent_workbench.adapters.config.app_data_dir", return_value=tmp_path),
        patch("agent_workbench.services.logging_setup.setup_logging"),
        patch("agent_workbench.adapters.ssl_setup.ensure_truststore"),
        patch.object(ui_launcher, "_run_chainlit") as run_chainlit,
    ):
        yield run_chainlit


def _report(exit_code: int) -> SimpleNamespace:
    return SimpleNamespace(exit_code=exit_code)


def test_failed_verify_prints_report_and_skips_chainlit(
    isolated: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch("agent_workbench.services.verify.run_verify", return_value=_report(1)),
        patch(
            "agent_workbench.interfaces.verify_formatting.format_report",
            return_value="FORMATTED REPORT",
        ),
    ):
        assert ui_launcher.main([]) == 1
    assert "FORMATTED REPORT" in capsys.readouterr().out
    isolated.assert_not_called()


def test_passed_verify_starts_chainlit(
    isolated: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    os.environ["CHAINLIT_HOST"] = ALL_INTERFACES
    with patch("agent_workbench.services.verify.run_verify", return_value=_report(0)):
        assert ui_launcher.main([]) == 0
    assert capsys.readouterr().out == ""
    isolated.assert_called_once()
    (target,) = isolated.call_args.args
    assert target.endswith("ui_target.py")
    assert os.environ["CHAINLIT_HOST"] == "127.0.0.1"
    root = Path(os.environ["CHAINLIT_APP_ROOT"])
    assert root.is_relative_to(tmp_path)
    assert Path(os.environ["CHAINLIT_ENV_FILE"]).is_relative_to(tmp_path)
    assert (root / ".chainlit" / "config.toml").is_file()


def test_verify_runs_without_tool_connections() -> None:
    with patch(
        "agent_workbench.services.verify.run_verify", return_value=_report(0)
    ) as run_verify:
        assert ui_launcher.main([]) == 0
    run_verify.assert_called_once_with(connect_tools=False)


def test_main_logs_to_app_log_file_at_info(tmp_path: Path) -> None:
    with (
        patch("agent_workbench.services.logging_setup.setup_logging") as setup_logging,
        patch("agent_workbench.services.verify.run_verify", return_value=_report(0)),
    ):
        assert ui_launcher.main([]) == 0
    setup_logging.assert_called_once()
    level, log_file = setup_logging.call_args.args
    assert level == "INFO"
    path = Path(log_file)
    assert path.parent == tmp_path / "logs"
    assert path.match("agent_workbench_ui_*.log")
    assert setup_logging.call_args.kwargs == {"console_level": "OUTPUT"}


def test_main_forwards_log_level_upper() -> None:
    with (
        patch("agent_workbench.services.logging_setup.setup_logging") as setup_logging,
        patch("agent_workbench.services.verify.run_verify", return_value=_report(0)),
    ):
        assert ui_launcher.main(["--log-level", "debug"]) == 0
    assert setup_logging.call_args.args[0] == "DEBUG"


@pytest.mark.usefixtures("restore_root_logging")
def test_main_creates_app_log_file(tmp_path: Path) -> None:
    with (
        patch(
            "agent_workbench.services.logging_setup.setup_logging", real_setup_logging
        ),
        patch("agent_workbench.services.verify.run_verify", return_value=_report(0)),
    ):
        assert ui_launcher.main([]) == 0
    assert [p.name for p in (tmp_path / "logs").glob("agent_workbench_ui_*.log")]


def test_app_log_file_is_timestamped_under_logs(tmp_path: Path) -> None:
    path = ui_launcher.app_log_file(tmp_path)
    assert path.parent == tmp_path / "logs"
    assert re.fullmatch(r"agent_workbench_ui_\d{8}_\d{6}\.log", path.name)


@pytest.mark.parametrize(
    "missing", ["langgraph", "langgraph.checkpoint.sqlite", "greenlet", "aiohttp"]
)
def test_missing_dependency_exits_before_verify(
    isolated: MagicMock, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    def find_spec(name: str) -> ModuleSpec | None:
        return None if name == missing else _real_find_spec(name)

    with (
        patch.object(ui_launcher, "find_spec", side_effect=find_spec),
        patch("agent_workbench.services.verify.run_verify") as run_verify,
    ):
        assert ui_launcher.main([]) == 1
    err = capsys.readouterr().err
    assert f"'{missing}'" in err
    assert "agent-workbench[langchain]" in err
    run_verify.assert_not_called()
    isolated.assert_not_called()


def test_failed_toolset_build_exits_before_chainlit(
    isolated: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_config_file(tmp_path, {"fake": {}})
    with (
        patch("agent_workbench.services.verify.run_verify", return_value=_report(0)),
        patch(
            "agent_workbench.adapters.tools.build_toolsets",
            side_effect=ValueError("duplicate tool name 'x'"),
        ),
    ):
        assert ui_launcher.main([]) == 1
    err = capsys.readouterr().err
    assert "Building the tools failed" in err
    assert "duplicate tool name 'x'" in err
    isolated.assert_not_called()


def test_no_tools_table_skips_toolset_build(isolated: MagicMock) -> None:
    with (
        patch("agent_workbench.services.verify.run_verify", return_value=_report(0)),
        patch("agent_workbench.adapters.tools.build_toolsets") as build_toolsets,
    ):
        assert ui_launcher.main([]) == 0
    build_toolsets.assert_not_called()
    isolated.assert_called_once()


def test_tools_not_a_table_exits_before_chainlit(
    isolated: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "config.toml").write_text('tools = "x"\n', encoding="utf-8")
    with patch("agent_workbench.services.verify.run_verify", return_value=_report(0)):
        assert ui_launcher.main([]) == 1
    assert "Building the tools failed" in capsys.readouterr().err
    isolated.assert_not_called()


def test_built_toolsets_are_closed_before_chainlit(
    isolated: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_providers(monkeypatch, {"fake": new_provider()})
    write_config_file(tmp_path, {"fake": {}})
    calls = MagicMock()
    with (
        patch("agent_workbench.services.verify.run_verify", return_value=_report(0)),
        patch(
            "agent_workbench.services.logging_setup.clamp_loggers",
            calls.clamp_loggers,
        ),
        patch("agent_workbench.adapters.tools.build_toolsets", calls.build_toolsets),
    ):
        assert ui_launcher.main([]) == 0
    assert [name for name, _, _ in calls.mock_calls][:2] == [
        "clamp_loggers",
        "build_toolsets",
    ]
    calls.clamp_loggers.assert_called_once_with(["tests"])
    calls.build_toolsets.return_value.close.assert_called_once_with()
    isolated.assert_called_once()
