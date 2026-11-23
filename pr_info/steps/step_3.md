# Step 3 – PERMISSIONS section in `verify`; remove `ui_launcher._check_toolsets`

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`), and issue #18
(Scope "`verify`"). Implement step 3 only, test first. Run pylint, pytest
(`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and lint-imports until all
pass. One commit.

## WHERE
- `src/agent_workbench/services/verify.py`
- `src/agent_workbench/interfaces/verify_formatting.py`
- `src/agent_workbench/apps/ui_launcher.py`
- `src/agent_workbench/apps/tool_setup.py` (docstring only)
- Tests: new `tests/services/test_verify_permissions.py`, `tests/services/test_verify.py`
  (`compute_exit_code`), `tests/interfaces/test_verify_formatting.py`,
  `tests/apps/test_ui_launcher.py`

## WHAT
`services/verify.py`:
```python
def verify_permissions(
    config_file: adapters_config.ConfigFile, *, tools_has_error: bool
) -> tuple[list[dict[str, str]], bool]:
    """PERMISSIONS rows ({"label", "status", "value"}) and whether any is an error."""
```
`VerifyReport` gains `permissions_entries: list[dict[str, str]] = field(default_factory=list)`
and `permissions_has_error: bool = False`.
`compute_exit_code(..., tools_has_error: bool = False, permissions_has_error: bool = False)`
returns 1 also when `permissions_has_error`.
`run_verify` calls `verify_permissions(config_file, tools_has_error=tools_has_error)` right
after `verify_tools` and fills the new fields and the exit code.

Imports: `from agent_workbench.services.permissions import parse_permissions` and the existing
`toolset_providers` (now holding `build_toolsets`). Never `adapters.tools` (contract from step 2).

## ALGORITHM
```
if parse_error: return [row("[permissions]", "info", "not checked – invalid config file")], False
if not config_file.tools and not config_file.tools_type_error:
    return [row("[permissions]", "info", "not checked – no [tools]")], False
try: toolsets = toolset_providers.build_toolsets(config_file)
except Exception as exc:  # every build error, never a crash
    if tools_has_error: return [row(..., "info", "not checked – fix the TOOLS errors first")], False
    return [row(..., "error", f"building the tools failed: {type(exc).__name__}: {exc}")], True
try: config, problems = parse_permissions(config_file.permissions, config_file.permissions_type_error,
                                          {s.name: s.group for s in toolsets.specs})
finally: toolsets.close()
rows = [_row(label, status, message) for label, status, message in problems]
rows += [_row("[permissions]", "info", f"{s.name} {mode} ({source})") per spec, mode/source from config.mode_of]
return rows, any(r["status"] == "error" for r in rows)
```
`parse_permissions` returns `ProblemRow` tuples; they are converted with `_row` first, so
`rows` holds only `{"label", "status", "value"}` dicts.
Source text: `tool`, `group <group>`, or `unlisted`. Info rows are added also when problems
contain errors. The build succeeding means PERMISSIONS is checked even if TOOLS has errors.

`verify_formatting.format_report`: after the TOOLS part add
`pad("PERMISSIONS")` and `format_config_section(report.permissions_entries)` (no new formatter).

`ui_launcher.py`:
- Delete `_check_toolsets` and its call in `main`; drop the `TYPE_CHECKING` `ConfigFile`
  import if unused.
- `main` docstring: "dependency check, `verify` (incl. the toolset build of its PERMISSIONS
  check), then Chainlit"; Returns: 1 on a missing dependency or a failed `verify`.
- Fix the comment before `read_config_file()`: `tool_setup` no longer pulls in
  `langchain_core` (after step 2); keep only the reason for clamping before verify.
`tool_setup.py` module docstring: "Toolset building of `get_runtime`" (no UI gate).

## DATA
PERMISSIONS rows use label `"[permissions]"`; values start with the key / tool name.

## Tests (write first)
`tests/services/test_verify_permissions.py` (fake provider via `tests.adapters.tool_fixtures`;
config text written directly for `[permissions]`):
- unknown tool name and unknown group name → warning rows, `has_error` False.
- unknown mode → error; unquoted dotted key → error with "quote group names";
  key both tool and group name → error; `permissions = "x"` → error.
- `[tools]` without `[permissions]` and with an empty `[permissions]` → the same warning.
- `[permissions]` without `[tools]` → info "not checked – no [tools]"; `build_toolsets` not called.
- invalid TOML → "not checked – invalid config file".
- build failure (fake provider `fail`) with clean TOOLS → error row; with `tools_has_error=True` → info "not checked".
- build succeeds although `tools_has_error=True` → permissions rows are produced.
- effective mode and source per tool (tool / group / unlisted); built toolsets are closed.
- `run_verify` with a PERMISSIONS error → `exit_code == 1` (patch provider checks and the test
  prompt as the existing `test_run_verify_tools_error_exits_1` does).
`tests/services/test_verify.py`: `compute_exit_code(..., permissions_has_error=True) == 1`.
`tests/interfaces/test_verify_formatting.py`: PERMISSIONS header and rows appear after TOOLS.
`tests/apps/test_ui_launcher.py`:
- Rewrite `test_failed_toolset_build_exits_before_chainlit`: real `run_verify`, with
  `agent_workbench.adapters.langchain._provider_checks.check_provider` patched to
  `{"overall_ok": True}` and `agent_workbench.services.verify._run_test_prompt` to `None`;
  a fake provider whose build fails → `main([]) == 1`, the report printed contains the
  PERMISSIONS error, Chainlit not started.
- Rewrite `test_tools_not_a_table_exits_before_chainlit` the same way (TOOLS error → exit 1).
- Delete `test_no_tools_table_skips_toolset_build` and `test_built_toolsets_are_closed_before_chainlit`
  (covered by the verify tests above; clamp-before-verify stays covered by
  `test_provider_loggers_clamped_before_verify`).
