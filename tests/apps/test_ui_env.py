"""Chainlit environment cleanup and ``config.toml`` writer of the UI launcher."""

import importlib
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_workbench.apps import ui_launcher
from agent_workbench.apps.ui_launcher import (
    AUTH_SECRET_FILE,
    CHAINLIT_HOST,
    DEFAULT_PORT,
    chainlit_port,
    prepare_chainlit_env,
    write_chainlit_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - the value the launcher must refuse


def test_app_root_and_env_file(tmp_path: Path) -> None:
    with patch.dict(os.environ):
        root = prepare_chainlit_env(tmp_path)
        assert root == tmp_path / "chainlit"
        assert root.is_dir()
        assert os.environ["CHAINLIT_APP_ROOT"] == str(root)
        env_file = Path(os.environ["CHAINLIT_ENV_FILE"])
        assert env_file.is_absolute()
        assert env_file.parent == root
        assert not env_file.exists()


def test_removed_env_vars_dropped_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    removed = ui_launcher._REMOVED_ENV_VARS  # pylint: disable=protected-access
    with patch.dict(os.environ, dict.fromkeys(removed, "x")):
        with caplog.at_level(logging.WARNING, logger=ui_launcher.__name__):
            prepare_chainlit_env(tmp_path)
        for var in removed:
            assert var not in os.environ
            assert any(var in record.getMessage() for record in caplog.records)


def test_removed_env_vars_matched_case_insensitively(tmp_path: Path) -> None:
    with patch.dict(os.environ, {"root": "x", "Chainlit_Server": "y"}):
        prepare_chainlit_env(tmp_path)
        assert not {"ROOT", "CHAINLIT_SERVER"} & {k.upper() for k in os.environ}


def test_unset_removed_env_vars_do_not_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    removed = ui_launcher._REMOVED_ENV_VARS  # pylint: disable=protected-access
    with patch.dict(os.environ):
        for var in removed:
            os.environ.pop(var, None)
        os.environ.pop("CHAINLIT_AUTH_SECRET", None)
        with caplog.at_level(logging.WARNING, logger=ui_launcher.__name__):
            prepare_chainlit_env(tmp_path)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_foreign_host_forced_to_loopback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.dict(os.environ, {"CHAINLIT_HOST": ALL_INTERFACES}):
        with caplog.at_level(logging.WARNING, logger=ui_launcher.__name__):
            prepare_chainlit_env(tmp_path)
        assert os.environ["CHAINLIT_HOST"] == CHAINLIT_HOST == "127.0.0.1"
    assert any(ALL_INTERFACES in record.getMessage() for record in caplog.records)


def test_auth_secret_created_then_reused(tmp_path: Path) -> None:
    with patch.dict(os.environ):
        os.environ.pop("CHAINLIT_AUTH_SECRET", None)
        prepare_chainlit_env(tmp_path)
        path = tmp_path / AUTH_SECRET_FILE
        secret = path.read_text(encoding="utf-8")
        assert secret
        assert os.environ["CHAINLIT_AUTH_SECRET"] == secret

        os.environ.pop("CHAINLIT_AUTH_SECRET")
        prepare_chainlit_env(tmp_path)
        assert path.read_text(encoding="utf-8") == secret
        assert os.environ["CHAINLIT_AUTH_SECRET"] == secret


@pytest.mark.parametrize("content", ["", " \n"], ids=["empty", "whitespace"])
def test_blank_auth_secret_file_regenerated(tmp_path: Path, content: str) -> None:
    path = tmp_path / AUTH_SECRET_FILE
    path.write_text(content, encoding="utf-8")
    with patch.dict(os.environ):
        os.environ.pop("CHAINLIT_AUTH_SECRET", None)
        prepare_chainlit_env(tmp_path)
        secret = path.read_text(encoding="utf-8")
        assert secret.strip()
        assert os.environ["CHAINLIT_AUTH_SECRET"] == secret


def test_foreign_auth_secret_replaced_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stored = "stored-secret-value"
    foreign = "foreign-secret-value"
    (tmp_path / AUTH_SECRET_FILE).write_text(stored, encoding="utf-8")
    with patch.dict(os.environ, {"CHAINLIT_AUTH_SECRET": foreign}):
        with caplog.at_level(logging.WARNING, logger=ui_launcher.__name__):
            prepare_chainlit_env(tmp_path)
        assert os.environ["CHAINLIT_AUTH_SECRET"] == stored
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("CHAINLIT_AUTH_SECRET" in message for message in messages)
    assert not any(stored in m or foreign in m for m in messages)


def test_matching_auth_secret_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stored = "stored-secret-value"
    (tmp_path / AUTH_SECRET_FILE).write_text(stored, encoding="utf-8")
    removed = ui_launcher._REMOVED_ENV_VARS  # pylint: disable=protected-access
    with patch.dict(os.environ, {"CHAINLIT_AUTH_SECRET": stored}):
        for var in (*removed, "CHAINLIT_HOST"):
            os.environ.pop(var, None)
        with caplog.at_level(logging.DEBUG, logger=ui_launcher.__name__):
            prepare_chainlit_env(tmp_path)
        assert os.environ["CHAINLIT_AUTH_SECRET"] == stored
    assert not caplog.records


def test_chainlit_port_default() -> None:
    with patch.dict(os.environ):
        os.environ.pop("CHAINLIT_PORT", None)
        assert chainlit_port() == DEFAULT_PORT == 8000


def test_chainlit_port_from_env() -> None:
    with patch.dict(os.environ, {"CHAINLIT_PORT": "8123"}):
        assert chainlit_port() == 8123


def test_written_config_loaded_by_chainlit() -> None:
    # load_settings() reads the file fixed at the first Chainlit import: the conftest's root.
    path = write_chainlit_config(Path(os.environ["CHAINLIT_APP_ROOT"]), 8123)
    assert path.name == "config.toml"
    assert path.parent.name == ".chainlit"

    from chainlit.config import (  # pylint: disable=import-outside-toplevel
        load_settings,
    )

    settings = load_settings()
    assert settings["project"].allow_origins == [
        "http://127.0.0.1:8123",
        "http://localhost:8123",
    ]
    assert settings["features"].spontaneous_file_upload.enabled is False
    assert settings["features"].edit_message is False
    assert settings["features"].mcp.enabled is False
    assert settings["features"].allow_thread_sharing is False
    assert settings["ui"].name == "agent-workbench"


def test_repo_root_untouched_by_chainlit_import() -> None:
    importlib.import_module("chainlit.config")
    assert not (REPO_ROOT / ".chainlit").exists()
    assert not (REPO_ROOT / ".files").exists()
