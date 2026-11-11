# Step 11 – Launcher gate: build and close the toolsets before Chainlit

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_11.md`), then implement
this step only. TDD: tests first. Run pylint, pytest (`-n auto -m "not integration"`) and
mypy; all must pass. One commit.

## WHERE
- `src/agent_workbench/apps/ui_launcher.py`
- `tests/apps/test_ui_launcher.py`

## WHAT
```python
def _check_toolsets() -> str | None:
    """Build the configured toolsets once and close them; return the error text or None.

    ``get_runtime`` runs only after Chainlit has started, so a broken tool setup must
    stop the launcher here. Cheap: SQL backends connect lazily, ``tool_specs`` has no
    side effects. Not called without a ``[tools]`` table.
    """
```

## HOW
- In `main`, after the `run_verify` gate and before `prepare_chainlit_env`:
  ```python
  error = _check_toolsets()
  if error:
      print(f"Building the tools failed: {error}", file=sys.stderr)
      return 1
  ```
- Imports inside the function (module must not import Chainlit or tool packages at load):
  `from agent_workbench.adapters import config as adapters_config`,
  `from agent_workbench.adapters import tools`; call `tools.build_toolsets(...)` through
  the module attribute so tests can patch `agent_workbench.adapters.tools.build_toolsets`.
- Update `main`'s docstring (dependency check, `verify`, toolset build, then Chainlit).

## ALGORITHM
```
config_file = adapters_config.read_config_file()
if not config_file.tools and not config_file.tools_type_error: return None   # a non-table [tools] reaches build_toolsets and fails
try: tools.build_toolsets(config_file).close()
except Exception as exc: return f"{type(exc).__name__}: {exc}"
return None
```

## Tests (`tests/apps/test_ui_launcher.py`, existing autouse fixture; `run_verify` patched to exit 0)
- `[tools]` in `tmp_path/config.toml`, `build_toolsets` patched to raise
  `ValueError("duplicate tool name 'x'")` → `main([]) == 1`, message on stderr,
  `_run_chainlit` not called.
- no `[tools]` table → `build_toolsets` (patched) not called, Chainlit started
  (do not rely on `sys.modules`: unreliable under xdist).
- `tools = "x"` (not a table), real `build_toolsets` → `main([]) == 1`, `_run_chainlit`
  not called.
- `[tools]` present, build succeeds → the returned object's `close()` called once, Chainlit
  started.

## DATA
`_check_toolsets` → `str | None`.
