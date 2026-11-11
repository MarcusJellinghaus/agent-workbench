# Step 12 – `verify` TOOLS section

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_12.md`), then implement
this step only. Follow `verify_config` and `format_config_section`. TDD: tests first. Run
pylint, pytest (`-n auto -m "not integration"`) and mypy; all must pass. One commit.

## WHERE
- `src/agent_workbench/services/verify.py`
- `src/agent_workbench/interfaces/verify_formatting.py`
- `tests/services/test_verify.py`, `tests/interfaces/test_verify_formatting.py`

## WHAT
```python
# services/verify.py
TOOL_PACKAGES: dict[str, tuple[str, str]] = {
    "sql": ("mcp_tools_sql", 'agent-workbench[sql] (or [sql-mssql] for SQL Server)'),
    "workspace": ("mcp_workspace", "agent-workbench[workspace]"),
}

def verify_tools(config_file: ConfigFile) -> tuple[list[dict[str, str]], bool]:
    """Check ``[tools]``: package installed, keys set, problems; no tool-specific checks.

    Returns:
        TOOLS rows (``{"label", "status", "value"}``) and whether any is an error.
    """

@dataclass
class VerifyReport:
    ...                                              # existing fields unchanged
    tools_entries: list[dict[str, str]] = field(default_factory=list)
    tools_has_error: bool = False

def compute_exit_code(
    config_has_error: bool, overall_ok: bool, test_prompt_ok: bool, tools_has_error: bool = False
) -> int: ...
```

## HOW
- Installed check: `importlib.util.find_spec(module) is None` on the top-level package
  (does not import it).
- `run_verify` calls `verify_tools(config_file)` after `verify_config` and fills the two
  fields; TOOLS errors make the exit code 1, so `agent-workbench-ui` stops at its existing
  `run_verify` gate.
- `format_report`: after the CONFIG section, `pad("TOOLS")` +
  `format_config_section(report.tools_entries)` (reuse; `[tools.sql]` labels group rows).
- Package verification rows are #27 – not here.

## ALGORITHM
```
if config_file.parse_error: return [row("[tools]", "info", "not checked – invalid config file")], False
if not config_file.tools and not config_file.tools_type_error: return [row("[tools]", "info", "not configured")], False
rows = []
for name, table in tools.items() if name in TOOL_PACKAGES and isinstance(table, dict):
    module, extra = TOOL_PACKAGES[name]
    rows += ok "package <module> installed" | error "package <module> not installed – install <extra>"
    rows += ok f"{key} configured" for each known key set
rows += [row(label, status, msg) for label, status, msg in tools_config_problems(config_file)]
return rows, any(r["status"] == "error" for r in rows)
```

## Tests
- `test_verify.py` (parametrized where possible; write TOML to the existing
  `config_path` fixture's file):
  - no `[tools]` → one info row "not configured", no error.
  - `[tools.sql]` with an absolute `query_config` and `find_spec` returning `None` for
    `mcp_tools_sql` → error row naming `[sql]` and `[sql-mssql]`; `run_verify().exit_code == 1`
    with the provider and test prompt passing.
  - relative path → error row; unknown key → warning row (exit code unaffected by the
    warning).
  - `[llm]` broken and `[tools]` valid → TOOLS rows still present.
  - `compute_exit_code(False, True, True, tools_has_error=True) == 1`.
- `test_verify_formatting.py`: the report contains `=== TOOLS` after CONFIG, rows grouped
  under `[tools.sql]` with `[OK]` / `[ERR]` / `[WARN]` markers.

## DATA
TOOLS row: `{"label": "[tools.sql]", "status": "error", "value": "package mcp_tools_sql
not installed – install agent-workbench[sql] (or [sql-mssql] for SQL Server)"}`.
