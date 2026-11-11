import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_workbench.services.logging_setup import (
    LOG_LEVELS,
    SIBLING_LOGGERS,
    setup_logging,
)

_EXPECTED_LEVELS = {
    "openai._base_client": logging.INFO,
    "urllib3.connectionpool": logging.INFO,
    "httpcore": logging.WARNING,
    "httpx": logging.WARNING,
}


@pytest.fixture(name="restore_levels")
def _restore_levels() -> Iterator[None]:
    names = [*_EXPECTED_LEVELS, *SIBLING_LOGGERS]
    previous = {name: logging.getLogger(name).level for name in names}
    yield
    for name, level in previous.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.usefixtures("restore_levels")
def test_setup_logging_calls_upstream_with_level() -> None:
    with patch(
        "agent_workbench.services.logging_setup._upstream_setup_logging"
    ) as upstream:
        setup_logging("DEBUG")
    upstream.assert_called_once_with("DEBUG", None, None)


@pytest.mark.usefixtures("restore_levels")
def test_setup_logging_forwards_file_and_console_level() -> None:
    with patch(
        "agent_workbench.services.logging_setup._upstream_setup_logging"
    ) as upstream:
        setup_logging("INFO", "app.log", console_level="OUTPUT")
    upstream.assert_called_once_with("INFO", "app.log", "OUTPUT")


@pytest.mark.usefixtures("restore_levels")
def test_setup_logging_quietens_sdk_loggers() -> None:
    for name in _EXPECTED_LEVELS:
        logging.getLogger(name).setLevel(logging.NOTSET)
    with patch("agent_workbench.services.logging_setup._upstream_setup_logging"):
        setup_logging("DEBUG")
    for name, level in _EXPECTED_LEVELS.items():
        assert logging.getLogger(name).level == level, name


@pytest.mark.usefixtures("restore_levels", "restore_root_logging")
@pytest.mark.parametrize("name", ["mcp_workspace", "mcp_tools_sql"])
def test_setup_logging_clamps_sibling_loggers(name: str) -> None:
    logging.getLogger(name).setLevel(logging.NOTSET)
    setup_logging("DEBUG")
    assert logging.getLogger(name).level == logging.INFO


@pytest.mark.usefixtures("restore_levels", "restore_root_logging")
def test_setup_logging_writes_info_to_log_file(tmp_path: Path) -> None:
    log_file = tmp_path / "x.log"
    setup_logging("INFO", str(log_file), console_level="OUTPUT")
    logging.getLogger("agent_workbench.test").info("app log record")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_file.is_file()
    assert "app log record" in log_file.read_text(encoding="utf-8")


@pytest.mark.usefixtures("restore_levels", "restore_root_logging")
def test_basic_config_after_setup_logging_adds_no_handler(tmp_path: Path) -> None:
    setup_logging("INFO", str(tmp_path / "x.log"), console_level="OUTPUT")
    handlers = logging.getLogger().handlers[:]
    logging.basicConfig()
    assert logging.getLogger().handlers == handlers


def test_log_levels_match_mcp_coder() -> None:
    assert LOG_LEVELS == ("DEBUG", "INFO", "OUTPUT", "WARNING", "ERROR", "CRITICAL")
