# Step 8 – Launcher `main` and the `agent-workbench-ui` script

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 8: `main()` of
`agent-workbench-ui` in `apps/ui_launcher.py` (dependency check, full `verify`, Chainlit
environment and config, `run_chainlit`), the console script and the `chainlit` core
dependency. Tests first, then code; all checks pass; one commit.

## Precondition
`chainlit`, `langgraph` and `langchain_core` resolvable; otherwise write one line to
`pr_info/.blocked.txt` and stop.

## WHERE
- Modify `src/agent_workbench/apps/ui_launcher.py`
- Modify `pyproject.toml`, `.importlinter`
- Create `tests/apps/test_ui_launcher.py`

## Packaging / contracts
- `dependencies`: `"chainlit>=<version found in step 7's probe>",   # chat UI (apps)`.
  `requires-python` unchanged.
- `[project.scripts]`: `agent-workbench-ui = "agent_workbench.apps.ui_launcher:main"`.
- `.importlinter`: `chainlit_isolation` contract (forbidden `chainlit` from
  `agent_workbench`, `ignore_imports = agent_workbench.apps.** -> chainlit`), comment
  "chainlit: the chat UI. Allowed in apps only."

## WHAT
```python
_UI_DEPENDENCIES = ("langgraph", "langchain_core")

def _missing_dependency() -> str | None: ...
def _run_chainlit(target: str) -> None:
    """Import chainlit.cli here only: it applies nest_asyncio and logging.basicConfig."""
def main(argv: list[str] | None = None) -> int: ...
```

## HOW
- Order as `interfaces.cli.main`: UTF-8 `reconfigure` of stdout / stderr; argparse
  (`prog="agent-workbench-ui"`, `--log-level` like the CLI, using `LOG_LEVELS`);
  `services.logging_setup.setup_logging`; `adapters.ssl_setup.ensure_truststore()`.
- Dependency check: own function (mcp_coder's `_check_agent_dependencies` is not copied),
  `importlib.util.find_spec(name) is None` → message
  `Missing package '<name>'. Install it with: pip install "agent-workbench[langchain]"`
  printed to stderr, exit 1.
- `services.verify.run_verify()` (full checks incl. the 30 s test prompt); on
  `exit_code == 1` print `interfaces.verify_formatting.format_report(report)` and return 1
  without touching Chainlit. On success print nothing.
- Then `prepare_chainlit_env(adapters.config.app_data_dir())`,
  `write_chainlit_config(root, chainlit_port())`,
  `_run_chainlit(str(Path(__file__).with_name("ui_target.py")))` (the shim follows in
  step 9; tests patch `_run_chainlit`), return 0.
- `_run_chainlit`: `from chainlit.cli import run_chainlit` inside the function, then
  `run_chainlit(target)` (opens the browser, blocks).
- Imports of `services` / `interfaces` modules inside `main`, as the CLI does, so importing
  `ui_launcher` stays light (the conftest imports it).

## ALGORITHM
```
utf-8 stdout/stderr; args = parser.parse_args(argv); setup_logging(args.log_level); ensure_truststore()
if (name := _missing_dependency()): print(msg, file=sys.stderr); return 1
report = run_verify(); if report.exit_code: print(format_report(report)); return 1
root = prepare_chainlit_env(app_data_dir()); write_chainlit_config(root, chainlit_port())
_run_chainlit(str(Path(__file__).with_name("ui_target.py"))); return 0
```

## DATA
Exit code `int`: 0 after Chainlit returns, 1 on missing dependency or failed `verify`.

## Tests (`tests/apps/test_ui_launcher.py`)
Autouse fixture: `patch.dict(os.environ)`, `app_data_dir` patched to `tmp_path`,
`setup_logging` and `ensure_truststore` patched; `_run_chainlit` always patched (tests never
import `chainlit.cli` or run Chainlit's server lifespan).
- `verify` exit code 1 → returns 1, the formatted report printed, `_run_chainlit` not called.
- `verify` passes → nothing printed, `_run_chainlit` called once with a path ending in
  `ui_target.py`; `CHAINLIT_HOST` is `127.0.0.1` even when set to `0.0.0.0` before; app root
  and env file inside `tmp_path`; `config.toml` written.
- `find_spec` patched to return None for `langgraph` → returns 1, stderr names `langgraph`
  and `agent-workbench[langchain]`, `run_verify` not called.

## Checks / commit
pylint, pytest, mypy, ruff, lint-imports, vulture, deptry, tach. Commit:
`feat(apps): agent-workbench-ui launcher`.
