"""Logging setup: mcp_coder_utils logging plus LLM-related third-party suppression."""

import logging

from mcp_coder_utils.log_utils import setup_logging as _upstream_setup_logging

LOG_LEVELS: tuple[str, ...] = (
    "DEBUG",
    "INFO",
    "OUTPUT",
    "WARNING",
    "ERROR",
    "CRITICAL",
)


def setup_logging(log_level: str) -> None:
    """Configure logging (mcp_coder_utils) and quieten SDK request logs."""
    _upstream_setup_logging(log_level)
    # INFO level
    logging.getLogger("openai._base_client").setLevel(logging.INFO)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

    # WARNING level
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
