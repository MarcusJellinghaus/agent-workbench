# Summary – #18 Permission modes per tool with confirmation dialog

Step 5 of epic #13. Replaces #17's hard-coded tool filter (`services/tool_filter.py`) with a
permission mode per tool or group, read from a top-level `[permissions]` table in
`~/.agent_workbench/config.toml`. `deny` tools are never bound; `ask` / `ask_session` tools show
a Chainlit OK/Cancel dialog; every call that does not run is logged; `verify` gets a
PERMISSIONS section.

The issue (#18) is the specification. These steps implement it; where a step is terse, the
issue's Scope, Constraints and Decisions apply.

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| Mode type | – | `core/permissions.py`: `PermissionMode` (`allow`, `ask`, `ask_session`, `deny`), `PERMISSION_MODES` |
| Config | `ConfigFile.tools` / `tools_type_error` | plus `ConfigFile.permissions` / `permissions_type_error`, same `_table` read, no second `tomllib` read |
| Parser / resolver | `services/tool_filter.py` (hard-coded groups) | `services/permissions.py`, pure: `parse_permissions(table, type_error, tools) -> (PermissionConfig, rows)`; `PermissionConfig.mode_of(tool, group) -> (mode, source)`; tool beats group; unlisted = `deny`. Removed: `tool_filter.py` |
| Toolset building | `adapters/tools.py` (imports `langchain_core`) | `Toolsets` / `build_toolsets` in `adapters/toolset_providers.py` (no `langchain_core`), so `services.verify` can build without the `[langchain-base]` extra |
| Enforcement | `ToolNode(tools, handle_tool_errors=True)` | `apps/permission_gate.py`: `make_tool_node(tools, modes)` → `ToolNode(..., awrap_tool_call=gate, wrap_tool_call=deny_sync)`. Per call: unbound → invalid arguments → mode |
| Binding | `enabled_specs` | `build_tools(toolsets, modes)` binds every spec whose mode is not `deny`; `build_graph(..., *, modes)` requires `{tool name: mode}` for every configured spec and raises `ValueError` for a bound tool missing or mapped to `deny` |
| Per-turn data | – | One frozen `TurnPermissions(confirm, grants, lock)` under one `configurable` key (`TURN_PERMISSIONS_KEY`), built by `run_turn`. None → every `ask` / `ask_session` call fails closed |
| Timer | idle paused from tool start to next model start | also paused while a dialog is open (`dialogs_open` counter in a `run_turn` closure) |
| Dialog | – | `ui_handlers.confirm_tool_call`: arguments message (JSON in a safe code fence), then `AskActionMessage` OK/Cancel, 300 s, cleanup on cancel. Grants: a `set` in `cl.user_session`, reset in `on_chat_resume` |
| Runtime | `Runtime.toolsets` | plus `Runtime.permissions` (kept for #19's Reload); `get_runtime` raises `ValueError` on PERMISSIONS errors (only with `[tools]`) |
| verify | CONFIG, TOOLS, … | plus PERMISSIONS (builds and closes the toolsets); `VerifyReport.permissions_entries` / `permissions_has_error`; `compute_exit_code` gets the flag |
| UI start | `ui_launcher._check_toolsets` | removed; verify's PERMISSIONS build fails the start on a build error |
| Contracts | – | import-linter: `services.permissions` imports only `core` (and no `langchain_core` / `langgraph` / `chainlit`); `services.verify` must not import `adapters.tools`. `tach.toml` unchanged |

### Log outcomes (`tool_calls.jsonl`)
`ok` / `error` / `cancelled` from `wrap_spec` (calls that ran) as before; new from the gate
(`result_size=None`, duration from gate entry to the decision): `denied` (Cancel, timeout, no
`TurnPermissions`, sync path), `blocked` (a `deny` tool of a configured provider),
`unknown_tool`, `invalid_arguments`, `dialog_error` (confirm callback raised), `cancelled`
(Stop during a dialog or while waiting for the dialog lock).

### Denial texts (mcp_coder wording)
- `DENY_USER`: "Tool call denied by the user. Do not retry this call — choose a different
  approach, or ask the user what they would prefer."
- `DENY_UNAVAILABLE`: "This tool requires approval, but no approval prompt was reachable, so
  the call was refused without asking the user. Choose a different approach or ask the user
  how to proceed."

Both as `ToolMessage(content=text, name=tool, tool_call_id=<call id>, status="error")`.

## Files created or modified

Created:
- `src/agent_workbench/core/permissions.py`
- `src/agent_workbench/services/permissions.py`
- `src/agent_workbench/apps/permission_gate.py`
- `tests/core/test_permissions.py`
- `tests/services/test_permissions.py`
- `tests/services/test_verify_permissions.py`
- `tests/apps/test_permission_gate.py`
- `tests/apps/test_ui_handlers_dialog.py`

Modified:
- `src/agent_workbench/adapters/config.py` – `permissions` fields
- `src/agent_workbench/adapters/toolset_providers.py` – receives `Toolsets` / `build_toolsets`
- `src/agent_workbench/adapters/tools.py` – loses them
- `src/agent_workbench/apps/agent.py` – `build_tools`, `build_graph`, `Runtime`, `_open_runtime`, `run_turn`
- `src/agent_workbench/apps/tool_setup.py` – import + docstring
- `src/agent_workbench/apps/ui_handlers.py` – dialog, grants
- `src/agent_workbench/apps/ui_launcher.py` – `_check_toolsets` removed, comment / docstrings
- `src/agent_workbench/services/verify.py` – PERMISSIONS section
- `src/agent_workbench/services/tool_call_log.py` – `elapsed` public, module docstring
- `src/agent_workbench/interfaces/verify_formatting.py` – PERMISSIONS section
- `.importlinter` – two contracts
- `tests/adapters/test_config.py`, `tests/adapters/test_tools.py`, `tests/adapters/test_toolset_providers.py`, `tests/adapters/tool_fixtures.py`
- `tests/apps/conftest.py` (autouse fixture: app data in `tmp_path`)
- `tests/apps/test_agent_tools.py`, `tests/apps/test_agent_graph.py`, `tests/apps/test_agent_turn.py`, `tests/apps/test_agent_checkpointer.py`, `tests/apps/test_ui_data_layer_delete.py`, `tests/apps/test_ui_handlers.py`, `tests/apps/test_ui_launcher.py`
- `tests/services/test_verify.py`, `tests/interfaces/test_verify_formatting.py`, `tests/test_tool_path_no_mcp.py`
- `README.md`, `docs/architecture/architecture.md`, `docs/security/security_design.md`

Deleted:
- `src/agent_workbench/services/tool_filter.py`
- `tests/services/test_tool_filter.py`

## Steps

1. Permission model: mode type, `[permissions]` reader, parser / resolver, purity contract.
2. Move `Toolsets` / `build_toolsets` to `adapters/toolset_providers.py`; verify guard contract.
3. PERMISSIONS section in `verify`; remove `ui_launcher._check_toolsets`.
4. Permission gate (`apps/permission_gate.py`) and `build_graph(..., modes=...)`.
5. Permissions drive binding and runtime; remove `services/tool_filter.py`.
6. Per-turn wiring in `run_turn`: `TurnPermissions`, timer pause while a dialog is open.
7. Chainlit dialog and `ask_session` grants in `ui_handlers`.
8. Docs: README, architecture, security design.

Manual smoke test (not a step): OK, Cancel, `ask_session`, Stop while the dialog is open, plus
the issue's "Smoke test also checks" list – documented in the PR description.
