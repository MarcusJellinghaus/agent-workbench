import logging
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from agent_workbench.services.logging_setup import LOG_LEVELS, setup_logging

_EXPECTED_LEVELS = {
    "openai._base_client": logging.INFO,
    "urllib3.connectionpool": logging.INFO,
    "httpcore": logging.WARNING,
    "httpx": logging.WARNING,
}


@pytest.fixture(name="restore_levels")
def _restore_levels() -> Iterator[None]:
    previous = {name: logging.getLogger(name).level for name in _EXPECTED_LEVELS}
    yield
    for name, level in previous.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.usefixtures("restore_levels")
def test_setup_logging_calls_upstream_with_level() -> None:
    with patch(
        "agent_workbench.services.logging_setup._upstream_setup_logging"
    ) as upstream:
        setup_logging("DEBUG")
    upstream.assert_called_once_with("DEBUG")


@pytest.mark.usefixtures("restore_levels")
def test_setup_logging_quietens_sdk_loggers() -> None:
    for name in _EXPECTED_LEVELS:
        logging.getLogger(name).setLevel(logging.NOTSET)
    with patch("agent_workbench.services.logging_setup._upstream_setup_logging"):
        setup_logging("DEBUG")
    for name, level in _EXPECTED_LEVELS.items():
        assert logging.getLogger(name).level == level, name


def test_log_levels_match_mcp_coder() -> None:
    assert LOG_LEVELS == ("DEBUG", "INFO", "OUTPUT", "WARNING", "ERROR", "CRITICAL")
