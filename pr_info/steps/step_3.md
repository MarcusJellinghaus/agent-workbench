# Step 3 – App log for the UI and clamped sibling loggers

## LLM prompt
Read `pr_info/steps/summary.md` (section "Logging strategy") and this file
(`pr_info/steps/step_3.md`), then implement this step only. Pattern: mcp-tools-sql
`src/mcp_tools_sql/main.py` (`_resolve_log_file`, `setup_logging(log_level, log_file,
console_level=...)`; reference project `mcp-tools-sql`). TDD: tests first. Run pylint,
pytest (`-n auto -m "not integration"`) and mypy; all must pass. One commit.
All logging goes through `mcp_coder_utils.log_utils` (via the `logging_setup` shim): if
this step needs something `log_utils` cannot do, stop and report instead of working
around it (the tool-call JSONL writer of step 7 is the only documented exception).

## WHERE
- `src/agent_workbench/services/logging_setup.py`
- `src/agent_workbench/apps/ui_launcher.py`
- `tests/services/test_logging_setup.py`, `tests/apps/test_ui_launcher.py`

## WHAT
```python
# services/logging_setup.py
SIBLING_LOGGERS: tuple[str, ...] = ("mcp_workspace", "mcp_tools_sql")

def setup_logging(
    log_level: str, log_file: str | None = None, console_level: str | None = None
) -> None:
    """Configure logging (mcp_coder_utils), quieten SDK logs, clamp sibling loggers."""

# apps/ui_launcher.py
def app_log_file(app_data: Path) -> Path:
    """Return ``<app_data>/logs/agent_workbench_ui_<YYYYmmdd_HHMMSS>.log``."""
```

## HOW
- `setup_logging` passes `log_level, log_file, console_level` to
  `_upstream_setup_logging`, keeps the existing SDK level lines, then
  `logging.getLogger(name).setLevel(logging.INFO)` for each of `SIBLING_LOGGERS`, with a
  comment: at DEBUG they log full tool parameters and results unredacted.
- `ui_launcher.main`:
  - `--log-level` default `"INFO"` (help text says so).
  - Move `from agent_workbench.adapters.config import app_data_dir` to before
    `setup_logging`; call
    `setup_logging(args.log_level, str(app_log_file(app_data_dir())), console_level="OUTPUT")`.
  - Reuse the `app_data_dir()` value later for `prepare_chainlit_env`.
- `verify` / `prompt` (`interfaces/cli.py`) unchanged: console only.

## ALGORITHM
```
app_log_file(app_data):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return app_data / "logs" / f"agent_workbench_ui_{stamp}.log"
```
(`setup_logging` upstream creates the folder.)

## Tests
Tests calling the real `setup_logging` must save `logging.getLogger().handlers` and the
root level, and in teardown remove/close every added handler and restore them (a fixture
in `test_logging_setup.py`); Windows cannot delete an open log file.
- `test_logging_setup.py`:
  - with `log_file=tmp_path/"x.log"`, `console_level="OUTPUT"`: a record at INFO lands in
    the file; the file exists.
  - after `setup_logging("DEBUG")`, `logging.getLogger("mcp_workspace").level ==
    logging.INFO` and the same for `mcp_tools_sql` (parametrize).
  - after `setup_logging(...)`, `logging.basicConfig()` adds no root handler (Chainlit
    calls it; confirms it is a no-op).
- `test_ui_launcher.py` (its autouse fixture patches `setup_logging` and `app_data_dir`):
  - `main([])` calls `setup_logging` with `"INFO"`, a path under `tmp_path / "logs"`
    named `agent_workbench_ui_*.log`, and `console_level="OUTPUT"`.
  - `main(["--log-level", "debug"])` passes `"DEBUG"`.
  - one test with the real `setup_logging` (fixture restoring handlers) asserts the app-log
    file is created.

## DATA
`app_log_file` → `Path`.
