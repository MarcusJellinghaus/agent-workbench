"""``main`` of ``agent-workbench-ui``: dependency check, ``verify``, Chainlit start."""

import importlib.util
import os
from collections.abc import Iterator
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent_workbench.apps import ui_launcher

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


@pytest.mark.parametrize("missing", ["langgraph", "langgraph.checkpoint.sqlite"])
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
