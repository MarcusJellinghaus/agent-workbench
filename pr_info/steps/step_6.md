# Step 6 – Tool-call log and `wrap_spec`

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`), then implement
this step only. Pattern for the hand-written JSONL writer: mcp_coder
`src/mcp_coder/icoder/core/event_log.py` (reference project `mcp_coder`) – but open, append
and close per write. TDD: tests first. Run pylint, pytest (`-n auto -m "not integration"`),
mypy and lint-imports; all must pass. One commit.
The hand-written JSONL writer is the one documented exception to "all logging via
`mcp_coder_utils.log_utils`"; app-log messages (e.g. a failed write) still go through
the standard `logging` module. If this step needs anything else `log_utils` cannot do,
stop and report instead of working around it.

## WHERE
- new `src/agent_workbench/services/tool_call_log.py` (no `langchain_core`)
- new `tests/services/test_tool_call_log.py`

## WHAT
```python
MAX_PARAM_CHARS = 200
LOG_FILE_NAME = "tool_calls.jsonl"

def truncate_text(text: str, limit: int = MAX_PARAM_CHARS) -> str:
    """Return *text* cut to *limit* characters with its full length noted."""

def sanitize_params(value: Any) -> Any:
    """Redact sensitive keys and cut long strings, recursively through dicts and lists."""

def tool_call_log_path() -> Path:
    """Return ``<app-data>/logs/tool_calls.jsonl``."""

def log_tool_call(
    tool: str,
    params: Mapping[str, Any],
    outcome: str,              # "ok" | "error" | "cancelled" | e.g. "denied" (#18)
    result_size: int | None,
    duration_s: float,
) -> None:
    """Append one JSON line; a failed write is logged to the app log, never raised."""

def wrap_spec(spec: "ToolSpec") -> "ToolSpec":
    """Return *spec* with ``fn`` wrapped so every call is logged.

    A sync ``fn`` stays sync, an async one stays async; the result is returned unchanged.
    """
```

## HOW
- Module docstring documents: the one exception to "all logging via `log_utils`"
  (`log_utils` configures only the root logger and cannot write a separate file independent
  of `--log-level`); never the result; over-redaction accepted (e.g. `max_tokens`
  contains `token`); secrets inside free text (SQL literals, file content) are not
  detected; not logged here: calls failing in `ToolNode` before `fn` runs (invalid
  arguments, unknown tool – #18's permission node logs them); errors a tool returns as
  text log as `ok`; a sync tool still running after Stop logs `ok` later.
- `from agent_workbench.adapters import config` and resolve the path through
  `config.app_data_dir()` at every write (tests patch it).
- `from agent_workbench.adapters.redaction import REDACTED_VALUE, SENSITIVE_KEY_PATTERNS`;
  `from agent_workbench.adapters.tool_results import result_text`;
  `ToolSpec` only under `TYPE_CHECKING`; `dataclasses.replace(spec, fn=wrapper)`.
- `_write_lock = threading.Lock()`: sync tools run in executor threads and `ToolNode`
  runs calls concurrently.
- User: `getpass.getuser()`; timestamp `datetime.now(UTC).isoformat()`.

## ALGORITHM
```
sanitize_params(v):
    dict → {k: REDACTED_VALUE if any(p in str(k).lower() for p in SENSITIVE_KEY_PATTERNS) else sanitize_params(x)}
    list/tuple → [sanitize_params(x) for x in v];  str → truncate_text(v);  else v
truncate_text(t, n): t if len(t) <= n else f"{t[:n]}… [{len(t)} chars]"
log_tool_call: line = json.dumps({ts, user, tool, params: sanitize_params(dict(params)), outcome, result_size, duration_s}, ensure_ascii=False, default=str)
    try: with _write_lock: path.parent.mkdir(parents, exist_ok); with path.open("a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: logger.exception("Writing the tool-call log failed")
wrapper(**kw): start = monotonic(); try result = [await] fn(**kw)
    except CancelledError (async only): log "cancelled"; raise   |   except Exception: log "error"; raise
    log "ok", len(result_text(result)); return result
```
Use `functools.wraps(spec.fn)` on both wrappers; the async wrapper is an `async def`.

## Tests (`tests/services/test_tool_call_log.py`, patch `agent_workbench.adapters.config.app_data_dir` → `tmp_path`)
- `sanitize_params` (parametrized): `{"password": "x"}`, `{"API_KEY": "x"}`,
  `{"outer": {"db_token": "x"}}`, `{"items": [{"secret": "x"}]}` → redacted; `max_tokens`
  redacted (accepted over-redaction); a 250-char string → first 200 chars + `[250 chars]`,
  also nested in a list inside a dict; non-strings unchanged.
- sync spec wrapped: `not inspect.iscoroutinefunction(wrapped.fn)`, result unchanged, one
  line with `outcome == "ok"`, `result_size == len(result_text(result))`, `tool`, `user`,
  `params`, `duration_s`, a UTC timestamp; no result in the line.
- async spec wrapped: `inspect.iscoroutinefunction(wrapped.fn)`.
- raising tool → exception re-raised, `outcome == "error"`.
- async tool cancelled (task + `cancel()` while it awaits an `asyncio.Event`) →
  `CancelledError` propagates, `outcome == "cancelled"`.
- failed write (make `tmp_path / "logs"` a file) → no exception, `logger.exception`
  called (caplog), the tool's result still returned.
- `log_tool_call("x", {}, "denied", None, 0.0)` writes a line with `result_size: null`.
- 20 threads calling `log_tool_call` → 20 lines, each valid JSON.

## DATA
JSONL line:
`{"timestamp": "2026-…+00:00", "user": "…", "tool": "read_tables", "params": {...},
"outcome": "ok", "result_size": 123, "duration_s": 0.012}`
