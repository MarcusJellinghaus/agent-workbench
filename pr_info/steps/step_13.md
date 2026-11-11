# Step 13 – `verify` TOOLS section with the providers' rows

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_13.md`), then implement
this step only. Follow `verify_config` and `format_config_section`. TDD: tests first. Run
pylint, pytest (`-n auto -m "not integration"`) and mypy; all must pass. One commit.
This step also covers #27 (folded into #17): provider rows are rendered without
tool-specific logic.

## WHERE
- `src/agent_workbench/services/verify.py`
- `src/agent_workbench/interfaces/verify_formatting.py`
- `src/agent_workbench/apps/ui_launcher.py` (`run_verify` call)
- `tests/services/test_verify.py`, `tests/interfaces/test_verify_formatting.py`,
  `tests/apps/test_ui_launcher.py`

## WHAT
```python
# services/verify.py
def verify_tools(
    config_file: ConfigFile, *, connect: bool
) -> tuple[list[dict[str, str]], bool]:
    """Check ``[tools]``: shape, provider registered, then the provider's own ``verify`` rows.

    No tool-specific checks: rows come from ``ToolsetProvider.verify(connect=connect)``.

    Returns:
        TOOLS rows (``{"label", "status", "value"}``) and whether any is an error.
    """

@dataclass
class VerifyReport:
    ...                                              # existing fields unchanged
    tools_entries: list[dict[str, str]] = field(default_factory=list)
    tools_has_error: bool = False

def run_verify(check_models: bool = False, *, connect_tools: bool = True) -> VerifyReport: ...

def compute_exit_code(
    config_has_error: bool, overall_ok: bool, test_prompt_ok: bool, tools_has_error: bool = False
) -> int: ...
```

## HOW
- Provider lookup: `toolset_providers.provider_class(name)` (step 9); its `ValueError`
  message (registered names + install hint) becomes the error row.
- Provider rows: `cls(table).verify(connect=connect)` → one row per `VerifyItem`:
  `label = f"[tools.{name}]"`, `status = item.status` (`ok` / `warning` / `error`),
  `value = f"{item.name}: {item.message}"` plus `f" – {item.hint}"` when set. A provider
  `verify` raising (the contract says it doesn't) → one error row
  `"verify failed: <type>: <message>"`.
- `run_verify(connect_tools=...)` calls `verify_tools(config_file, connect=connect_tools)`
  after `verify_config` and fills the two fields; TOOLS errors make the exit code 1, so
  `agent-workbench-ui` stops at its existing `run_verify` gate.
- `agent-workbench verify` (`interfaces/cli.py`) keeps the default `connect_tools=True`;
  `ui_launcher.main` calls `run_verify(connect_tools=False)`: a database that is down must
  not block the UI start.
- `format_report`: after the CONFIG section, `pad("TOOLS")` +
  `format_config_section(report.tools_entries)` (reuse; `[tools.<name>]` labels group rows).

## ALGORITHM
```
if config_file.parse_error: return [row("[tools]", "info", "not checked – invalid config file")], False
if not config_file.tools and not config_file.tools_type_error: return [row("[tools]", "info", "not configured")], False
rows = [row(label, status, msg) for label, status, msg in tools_config_problems(config_file)]
for name, table in config_file.tools.items() if isinstance(table, dict):
    try: cls = provider_class(name)
    except ValueError as exc: rows.append(row(f"[tools.{name}]", "error", str(exc))); continue
    try: items = cls(table).verify(connect=connect)
    except Exception as exc: rows.append(row(..., "error", f"verify failed: ...")); continue
    rows += [row from item for item in items]
return rows, any(r["status"] == "error" for r in rows)
```

## Tests
- `test_verify.py` (fake providers from `tests/adapters/tool_fixtures.py`; write TOML to
  the existing `config_path` fixture's file):
  - no `[tools]` → one info row "not configured", no error, no provider loaded.
  - `[tools.fake]` whose fake provider returns an `ok`, a `warning` and an `error` row →
    three rows with those statuses and `name: message – hint` values;
    `run_verify().exit_code == 1` with the LLM provider and test prompt passing.
  - unregistered `[tools.x]` → error row naming the registered providers.
  - `connect` passed through: `run_verify()` → the fake provider saw `connect=True`;
    `run_verify(connect_tools=False)` → `connect=False`.
  - provider `verify` raising → one error row.
  - subtable not a table → error row.
  - `[llm]` broken and `[tools]` valid → TOOLS rows still present.
  - `compute_exit_code(False, True, True, tools_has_error=True) == 1`.
- `test_verify_formatting.py`: the report contains `=== TOOLS` after CONFIG, rows grouped
  under `[tools.fake]` with `[OK]` / `[ERR]` / `[WARN]` markers.
- `test_ui_launcher.py`: `run_verify` called with `connect_tools=False`.

## DATA
TOOLS row: `{"label": "[tools.sql]", "status": "error", "value": "config.query_config:
relative path not allowed – use an absolute path"}`.
