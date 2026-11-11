# Step 8 – Remove the hard-coded tool packages

## LLM prompt
Read `pr_info/steps/summary.md`, `pr_info/steps/Decisions.md` and this file
(`pr_info/steps/step_8.md`), then implement this step only. Tool packages become plugins
(step 9): agent-workbench must not name `mcp_tools_sql` / `mcp_workspace` or their config
keys. This step removes what steps 1, 3 and 4 hard-coded. TDD: adjust the tests first.
Run pylint, pytest (`-n auto -m "not integration"`), mypy and vulture
(`run_vulture_check`); all must pass. One commit.

## WHERE
- `pyproject.toml`
- `src/agent_workbench/adapters/config.py`
- `src/agent_workbench/services/logging_setup.py`
- `tests/adapters/test_config.py`, `tests/services/test_logging_setup.py`

## WHAT
```python
# adapters/config.py – kept: ConfigFile.tools / tools_type_error, _table, read_config_file
def tools_config_problems(config_file: ConfigFile) -> list[tuple[str, str, str]]:
    """Return ``(label, status, message)`` error rows for the shape of ``[tools]``.

    Only the shape is checked: ``[tools]`` and each ``[tools.<name>]`` must be tables.
    Keys and paths belong to the provider registered as ``<name>`` (its ``verify`` rows).
    """
```
Removed: `TOOL_KEYS`, `REQUIRED_TOOL_KEYS`, `tool_path`, `_with_hint` (if unused), the
`unknown_key_hint` import (if unused), `SIBLING_LOGGERS` and its loop in `setup_logging`,
the mypy override for `mcp_tools_sql` / `mcp_workspace` (step 1).

## HOW
- `tools_config_problems`: keep the `tools_type_error` row and the "expected table, got
  <type>" row per subtable. Drop unknown-table warnings (every name is a provider name;
  "no provider registered" is reported by discovery, step 9), required / unknown keys,
  string-type and relative-path checks. Update its docstring and the module docstring.
- `logging_setup.setup_logging`: drop the clamp loop and "clamp sibling loggers" from the
  docstring. Step 10 adds `clamp_loggers(names)` together with its caller.
- `pyproject.toml`: remove the `mcp_tools_sql` / `mcp_workspace` `[[tool.mypy.overrides]]`
  block.

## ALGORITHM
```
if tools_type_error: return [("[tools]", "error", tools_type_error)]
return [(f"[tools.{name}]", "error", f"expected table, got {type(t).__name__}")
        for name, t in config_file.tools.items() if not isinstance(t, dict)]
```

## Tests
- `test_config.py`: remove the `tool_path` test and the key / path / unknown-table cases.
  Keep reading `[tools.*]` into `ConfigFile.tools`, `tools = "x"` → `tools_type_error`,
  broken `[llm]` still reads `[tools]`. `tools_config_problems` (parametrized): valid
  tables → `[]`; `[tools.foo]` with any keys → `[]`; subtable not a table → error;
  `tools_type_error` → one error row. Use provider-neutral table names in new cases.
- `test_logging_setup.py`: remove `SIBLING_LOGGERS` from the imports and the expected
  levels, and remove the `mcp_workspace` / `mcp_tools_sql` parametrized test.

## DATA
Problem row: `("[tools.sql]", "error", "expected table, got str")`.
