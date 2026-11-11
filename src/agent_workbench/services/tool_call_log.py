"""Tool-call log: one JSON line per tool call in ``<app-data>/logs/tool_calls.jsonl``.

The hand-written JSONL writer is the one exception to "all logging via
``mcp_coder_utils.log_utils``": ``log_utils`` configures only the root logger and cannot
write a separate file independent of ``--log-level``. App-log messages (e.g. a failed
write) still go through ``logging``.

What a line holds: timestamp, user, tool, sanitized parameters, outcome, result size and
duration – never the result. Parameters are redacted by key name, so some harmless keys
are over-redacted (e.g. ``max_tokens`` contains ``token``); secrets inside free text (SQL
literals, file content) are not detected.

Not logged here: calls that fail in ``ToolNode`` before ``fn`` runs (invalid arguments,
unknown tool – #18's permission node logs them). An error a tool returns as text logs as
``ok``; a sync tool still running after Stop logs ``ok`` when it finishes.
"""

import asyncio
import dataclasses
import functools
import getpass
import inspect
import json
import logging
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_workbench.adapters import config
from agent_workbench.adapters.redaction import REDACTED_VALUE, SENSITIVE_KEY_PATTERNS
from agent_workbench.adapters.tool_results import result_text

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import ToolSpec

logger = logging.getLogger(__name__)

MAX_PARAM_CHARS = 200
LOG_FILE_NAME = "tool_calls.jsonl"

# Sync tools run in executor threads and ToolNode runs calls concurrently.
_write_lock = threading.Lock()


def truncate_text(text: str, limit: int = MAX_PARAM_CHARS) -> str:
    """Return *text* cut to *limit* characters with its full length noted.

    Args:
        text: The text to cut.
        limit: Maximum number of characters kept.

    Returns:
        *text* unchanged when it fits, else its first *limit* characters and its length.
    """
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… [{len(text)} chars]"


def sanitize_params(value: Any) -> Any:
    """Redact sensitive keys and cut long strings, recursively through dicts and lists.

    Args:
        value: Tool parameters, or a value nested in them.

    Returns:
        A sanitized copy; other values are returned unchanged.
    """
    if isinstance(value, dict):
        return {
            key: (
                REDACTED_VALUE
                if any(p in str(key).lower() for p in SENSITIVE_KEY_PATTERNS)
                else sanitize_params(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_params(item) for item in value]
    if isinstance(value, str):
        return truncate_text(value)
    return value


def tool_call_log_path() -> Path:
    """Return ``<app-data>/logs/tool_calls.jsonl``.

    Returns:
        The path of the tool-call log.
    """
    return config.app_data_dir() / "logs" / LOG_FILE_NAME


def log_tool_call(
    tool: str,
    params: Mapping[str, Any],
    outcome: str,
    result_size: int | None,
    duration_s: float,
) -> None:
    """Append one JSON line; a failed write is logged to the app log, never raised.

    Args:
        tool: Tool name.
        params: Arguments of the call; sanitized before writing.
        outcome: ``"ok"``, ``"error"``, ``"cancelled"`` or e.g. ``"denied"``.
        result_size: Length of the result text, or None without a result.
        duration_s: Duration of the call in seconds.
    """
    try:
        line = json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "user": getpass.getuser(),
                "tool": tool,
                "params": sanitize_params(dict(params)),
                "outcome": outcome,
                "result_size": result_size,
                "duration_s": duration_s,
            },
            ensure_ascii=False,
            default=str,
        )
        path = tool_call_log_path()
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Writing the tool-call log failed")


def _elapsed(start: float) -> float:
    """Return the seconds since *start* (``time.monotonic``), rounded to milliseconds."""
    return round(time.monotonic() - start, 3)


def wrap_spec(spec: "ToolSpec") -> "ToolSpec":
    """Return *spec* with ``fn`` wrapped so every call is logged.

    A sync ``fn`` stays sync, an async one stays async; the result is returned unchanged.

    Args:
        spec: The tool spec to wrap.

    Returns:
        A copy of *spec* with the logging ``fn``.
    """
    fn = spec.fn
    name = spec.name

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(**kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                result = await fn(**kwargs)
            except asyncio.CancelledError:
                log_tool_call(name, kwargs, "cancelled", None, _elapsed(start))
                raise
            except Exception:
                log_tool_call(name, kwargs, "error", None, _elapsed(start))
                raise
            log_tool_call(name, kwargs, "ok", len(result_text(result)), _elapsed(start))
            return result

        return dataclasses.replace(spec, fn=async_wrapper)

    @functools.wraps(fn)
    def sync_wrapper(**kwargs: Any) -> Any:
        start = time.monotonic()
        try:
            result = fn(**kwargs)
        except Exception:
            log_tool_call(name, kwargs, "error", None, _elapsed(start))
            raise
        log_tool_call(name, kwargs, "ok", len(result_text(result)), _elapsed(start))
        return result

    return dataclasses.replace(spec, fn=sync_wrapper)
