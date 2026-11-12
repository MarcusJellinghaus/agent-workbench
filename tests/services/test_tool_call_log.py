"""Tests for the tool-call log: redaction, truncation, JSONL writing and wrap_spec."""

import asyncio
import inspect
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from mcp_coder_utils.tool_spec import ToolSpec, tool_spec
from pydantic import BaseModel

from agent_workbench.adapters.tool_results import result_text
from agent_workbench.services import tool_call_log
from agent_workbench.services.tool_call_log import (
    log_tool_call,
    sanitize_params,
    tool_call_log_path,
    truncate_text,
    wrap_spec,
)

_LONG = "x" * 250
_CUT = f"{'x' * 200}… [250 chars]"


@pytest.fixture
def app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app-data folder at *tmp_path*."""
    monkeypatch.setattr(
        "agent_workbench.adapters.config.app_data_dir", lambda: tmp_path
    )
    return tmp_path


def _lines(app_data: Path) -> list[dict[str, Any]]:
    """Return the parsed lines of the tool-call log."""
    text = (app_data / "logs" / "tool_calls.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"password": "x"}, {"password": "***"}),
        ({"API_KEY": "x"}, {"API_KEY": "***"}),
        ({"outer": {"db_token": "x"}}, {"outer": {"db_token": "***"}}),
        ({"items": [{"secret": "x"}]}, {"items": [{"secret": "***"}]}),
        ({"max_tokens": 5}, {"max_tokens": "***"}),
        ({"query": _LONG}, {"query": _CUT}),
        ({"outer": {"items": ["a", _LONG]}}, {"outer": {"items": ["a", _CUT]}}),
        (
            {"n": 3, "f": 1.5, "b": True, "z": None},
            {"n": 3, "f": 1.5, "b": True, "z": None},
        ),
    ],
)
def test_sanitize_params(params: dict[str, Any], expected: dict[str, Any]) -> None:
    """Sensitive keys are redacted (also over-redacted) and long strings cut, recursively."""
    assert sanitize_params(params) == expected


class _Connection(BaseModel):
    """A nested tool argument; LangChain passes it on as a model instance."""

    password: str
    query: str


def test_sanitize_params_nested_model() -> None:
    """A nested pydantic model is redacted and cut like a dict."""
    params = {"conn": _Connection(password="hunter2", query=_LONG)}
    assert sanitize_params(params) == {"conn": {"password": "***", "query": _CUT}}


def test_sanitize_params_generic_mapping() -> None:
    """A non-dict mapping is redacted and cut like a dict."""
    params = {"outer": MappingProxyType({"api_key": "x", "query": _LONG})}
    assert sanitize_params(params) == {"outer": {"api_key": "***", "query": _CUT}}


def test_nested_model_argument_logged_sanitized(app_data: Path) -> None:
    """A model argument reaches the log line redacted and cut, not as its repr."""

    def connect(conn: _Connection) -> str:
        """Connect."""
        return "ok"

    wrap_spec(tool_spec(connect, group="g.read", read_only=True)).fn(
        conn=_Connection(password="hunter2", query=_LONG)
    )
    (line,) = _lines(app_data)
    assert line["params"] == {"conn": {"password": "***", "query": _CUT}}
    assert "hunter2" not in json.dumps(line)


def test_truncate_text_short_unchanged() -> None:
    """Text within the limit is returned as is."""
    assert truncate_text("abc", 3) == "abc"


def test_truncate_text_cut() -> None:
    """Longer text is cut to the limit and its full length noted."""
    assert truncate_text("abcdef", 3) == "abc… [6 chars]"


def test_tool_call_log_path(app_data: Path) -> None:
    """The log lives in the logs folder of the app-data folder."""
    assert tool_call_log_path() == app_data / "logs" / "tool_calls.jsonl"


def _sync_spec(result: Any) -> ToolSpec:
    """Return a sync spec returning *result*."""

    def lookup(count: int) -> Any:
        """Look something up."""
        del count
        return result

    return tool_spec(lookup, group="test.read", read_only=True)


def _async_spec(result: Any) -> ToolSpec:
    """Return an async spec returning *result*."""

    async def lookup(count: int) -> Any:
        """Look something up."""
        del count
        return result

    return tool_spec(lookup, group="test.read", read_only=True)


def test_sync_spec_logged(app_data: Path) -> None:
    """A sync tool stays sync, returns its result unchanged and logs one ok line."""
    result = {"rows": ["secret-result-value"]}
    before = datetime.now().astimezone()

    wrapped = wrap_spec(_sync_spec(result))
    returned = wrapped.fn(count=2)

    assert not inspect.iscoroutinefunction(wrapped.fn)
    assert returned is result
    [line] = _lines(app_data)
    assert line["tool"] == "lookup"
    assert line["user"]
    assert line["params"] == {"count": 2}
    assert line["outcome"] == "ok"
    assert line["result_size"] == len(result_text(result))
    assert line["duration_s"] >= 0
    timestamp = datetime.fromisoformat(line["timestamp"])
    assert timestamp.utcoffset() == timedelta(0)
    assert timestamp >= before - timedelta(seconds=1)
    assert "secret-result-value" not in json.dumps(line)


async def test_async_spec_logged(app_data: Path) -> None:
    """An async tool stays async and logs one ok line."""
    wrapped = wrap_spec(_async_spec("done"))

    returned = await wrapped.fn(count=1)

    assert inspect.iscoroutinefunction(wrapped.fn)
    assert returned == "done"
    [line] = _lines(app_data)
    assert line["outcome"] == "ok"
    assert line["result_size"] == 4


def test_wrapped_spec_keeps_other_fields(app_data: Path) -> None:
    """Only fn is replaced."""
    del app_data
    spec = _sync_spec("ok")

    wrapped = wrap_spec(spec)

    assert wrapped.name == spec.name
    assert wrapped.args_model is spec.args_model
    assert wrapped.fn is not spec.fn
    assert wrapped.fn.__name__ == spec.fn.__name__


def test_sync_error_logged(app_data: Path) -> None:
    """A raising sync tool re-raises and logs an error line."""

    def broken(count: int) -> str:
        """Fail."""
        raise ValueError(f"bad {count}")

    wrapped = wrap_spec(tool_spec(broken, group="test.read", read_only=True))

    with pytest.raises(ValueError, match="bad 1"):
        wrapped.fn(count=1)

    [line] = _lines(app_data)
    assert line["outcome"] == "error"
    assert line["result_size"] is None


async def test_async_error_logged(app_data: Path) -> None:
    """A raising async tool re-raises and logs an error line."""

    async def broken(count: int) -> str:
        """Fail."""
        raise ValueError(f"bad {count}")

    wrapped = wrap_spec(tool_spec(broken, group="test.read", read_only=True))

    with pytest.raises(ValueError, match="bad 1"):
        await wrapped.fn(count=1)

    [line] = _lines(app_data)
    assert line["outcome"] == "error"


async def test_async_cancelled_logged(app_data: Path) -> None:
    """A cancelled async tool propagates CancelledError and logs a cancelled line."""
    started = asyncio.Event()
    never = asyncio.Event()

    async def waiting(count: int) -> str:
        """Wait forever."""
        del count
        started.set()
        await never.wait()
        return "unreachable"

    wrapped = wrap_spec(tool_spec(waiting, group="test.read", read_only=True))
    task = asyncio.create_task(wrapped.fn(count=1))
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    [line] = _lines(app_data)
    assert line["outcome"] == "cancelled"
    assert line["result_size"] is None


def test_failed_write_not_raised(
    app_data: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed write goes to the app log; the tool's result is still returned."""
    (app_data / "logs").write_text("not a folder", encoding="utf-8")
    wrapped = wrap_spec(_sync_spec("still here"))

    with caplog.at_level(logging.ERROR, logger=tool_call_log.__name__):
        returned = wrapped.fn(count=1)

    assert returned == "still here"
    assert any(
        record.message == "Writing the tool-call log failed" and record.exc_info
        for record in caplog.records
    )


def test_log_tool_call_without_result_size(app_data: Path) -> None:
    """A call without a result (e.g. denied) logs result_size null."""
    log_tool_call("x", {}, "denied", None, 0.0)

    [line] = _lines(app_data)
    assert line["tool"] == "x"
    assert line["params"] == {}
    assert line["outcome"] == "denied"
    assert line["result_size"] is None
    assert line["duration_s"] == 0.0


def test_log_tool_call_concurrent(app_data: Path) -> None:
    """Concurrent writes from threads produce one valid JSON line each."""
    threads = [
        threading.Thread(
            target=log_tool_call, args=(f"t{i}", {"text": _LONG}, "ok", i, 0.1)
        )
        for i in range(20)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = _lines(app_data)
    assert len(lines) == 20
    assert {line["tool"] for line in lines} == {f"t{i}" for i in range(20)}
