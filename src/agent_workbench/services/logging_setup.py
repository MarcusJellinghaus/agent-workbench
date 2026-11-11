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

SIBLING_LOGGERS: tuple[str, ...] = ("mcp_workspace", "mcp_tools_sql")


def setup_logging(
    log_level: str, log_file: str | None = None, console_level: str | None = None
) -> None:
    """Configure logging (mcp_coder_utils), quieten SDK logs, clamp sibling loggers.

    Args:
        log_level: Level of the file sink, and of the console when no
            ``console_level`` is given.
        log_file: Optional path of a JSON log file; without it, console only.
        console_level: Optional level of a console sink alongside the file.
    """
    _upstream_setup_logging(log_level, log_file, console_level)
    # INFO level
    logging.getLogger("openai._base_client").setLevel(logging.INFO)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

    # WARNING level
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # At DEBUG the tool packages log full tool parameters and results unredacted.
    for name in SIBLING_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
