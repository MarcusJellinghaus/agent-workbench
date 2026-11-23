# Step 5 – Permissions drive binding and runtime; remove `services/tool_filter.py`

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`), and issue #18
(Scope "Binding", "Layers / contracts"). Implement step 5 only, test first. Run pylint,
pytest (`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and lint-imports until
all pass. One commit.

## WHERE
- `src/agent_workbench/apps/agent.py`
- Delete `src/agent_workbench/services/tool_filter.py`, `tests/services/test_tool_filter.py`
- Tests: `tests/apps/test_agent_tools.py`, `tests/apps/test_ui_handlers.py`,
  `tests/test_tool_path_no_mcp.py`

## WHAT
```python
def tool_modes(permissions: PermissionConfig, specs: Iterable[ToolSpec]) -> dict[str, PermissionMode]:
    """{spec name: effective mode} for every spec, deny included."""

def build_tools(toolsets: Toolsets, modes: Mapping[str, PermissionMode]) -> list[StructuredTool]:
    """Wrapped and adapted tools for every spec whose mode is not deny, in spec order."""

def _runtime_permissions(config_file: ConfigFile, toolsets: Toolsets) -> PermissionConfig:
    """Parse [permissions]; raise ValueError on its error rows (warnings never raise)."""
```
`Runtime` gains `permissions: PermissionConfig | None = None` (None without `[tools]`; kept
for #19's Reload; docstring updated).

## ALGORITHM
`_open_runtime` after `build_configured_toolsets`:
```
if toolsets is None: permissions, modes = None, {}
else:
    permissions = _runtime_permissions(config_file, toolsets)
    modes = tool_modes(permissions, toolsets.specs)
tools = build_tools(toolsets, modes) if toolsets is not None else []
graph = build_graph(chat_model, tools, saver, modes=modes)
```
`_runtime_permissions`: `parse_permissions(cf.permissions, cf.permissions_type_error,
{s.name: s.group for s in toolsets.specs})`; errors = `[f"{label} {msg}" for label, status,
msg in rows if status == "error"]`; raise `ValueError("Invalid [permissions] config: " +
"; ".join(errors))` if any. Called inside the existing `try`, so toolsets and checkpointer
are closed on the error. Without `[tools]`, `[permissions]` is not checked.

`build_tools`: `[to_structured_tool(wrap_spec(s)) for s in toolsets.specs if modes[s.name] != "deny"]`.

## HOW
- Remove the transitional `enabled_specs` code from step 4 and the `tool_filter` import.
- `get_runtime` docstring: also raises `ValueError` for an invalid `[permissions]` (with `[tools]`).
- `tests/test_tool_path_no_mcp.py` `_SCRIPT`: replace `enabled_specs` with
  `parse_permissions` from `services.permissions` (a small inline `[permissions]` table
  allowing `sql.schema` and `workspace.read`) and `mode_of`; module docstring "filter" →
  "permissions". It still imports no `agent_workbench.apps`.
- Verify the rewritten `_SCRIPT` explicitly (subprocess, `integration`-marked, so the
  step's `-m "not integration"` run skips it):
  `mcp__mcp-tools-py__run_pytest_check(markers=["integration"], extra_args=["tests/test_tool_path_no_mcp.py"])`.
  It must pass: the script builds the toolsets, calls `read_tables` / `list_directory`
  and imports no `mcp`. Exception: a skip because `sql` / `workspace` are not registered in
  the `agent_workbench.toolsets` entry-point group counts as done – neither provider
  registers yet (mcp-workspace #393, mcp-tools-sql #107). Record the run as deferred in
  the commit message; any other skip or failure blocks the step.

## DATA
`modes` as in step 4; `Runtime.permissions: PermissionConfig | None`.

## Tests (write first) – `tests/apps/test_agent_tools.py`
- `write_config_file` in `tests/adapters/tool_fixtures.py` gets an optional
  `permissions: dict[str, str] | None = None` parameter writing a `[permissions]` table with
  quoted keys.
- Replace `test_only_enabled_tools_are_bound` / `_FILTER_TABLES`: with the README default
  block (`"sql.schema"`, `validate_sql`, `"workspace.read"`, `"workspace.write"` → `allow`)
  `get_runtime` binds `read_tables`, `validate_sql`, `read_file`, `save_file` only.
- `deny` tool not bound; `ask` / `ask_session` tools bound; tool-level `deny` overrides an
  `allow` group.
- Invalid `[permissions]` (unknown mode) with `[tools]` → `get_runtime` raises `ValueError`,
  toolsets and checkpointer closed; invalid `[permissions]` without `[tools]` → no raise;
  an unknown key (warning) → no raise.
- `runtime.permissions` holds the parsed config.
- Existing tests that call `build_tools` (`_run_loop`, `test_ui_handlers.py`'s fake-provider
  test) pass `modes` explicitly (e.g. `tool_modes(PermissionConfig({"workspace.read": "allow"}), toolsets.specs)`).
