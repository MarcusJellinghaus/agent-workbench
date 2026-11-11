# Summary – #17 Tools in the agent: adapter, tool config and logging

Step 4 of epic #13. The model gets the tools of every configured tool package in-process,
through their `ToolSpec` export – no MCP. Tool packages are **plugins**: each registers a
`ToolsetProvider` (mcp-coder-utils#61) under an entry point in the
`agent_workbench.toolsets` group, and `[tools.<name>]` selects and configures provider
`<name>` (pattern: mcp_coder's `mcp_coder.toolkits`). agent-workbench names no tool
package in its code and needs none to be tested (fake provider). Every call that runs is
logged to a JSONL file. `verify` and the UI launcher gate on the providers.
Read issue #17 for the full requirement list and `Decisions.md` for the plugin-model
revision; this plan implements it with the simplifications agreed in the plan review (no
new `core` type, one shape-check function, per-write file open, one truncation function,
pause the inactivity timer from tool start to the next model start).

## Architectural / design changes

### Data flow of a tool

```
~/.agent_workbench/config.toml [tools.<name>]
   │ adapters.config.read_config_file → ConfigFile.tools (+ tools_type_error)
   │ adapters.config.tools_config_problems   (shape only; shared by verify and the build)
   ▼
adapters.toolset_providers.provider_class(name)   # entry point <name> in agent_workbench.toolsets
   │ provider = cls(table); provider.verify(connect) → rows (verify) / provider.build()
   ▼
adapters.tools.build_toolsets(config_file) → Toolsets(specs, toolsets)  # one ToolCollector
   │                                                                     # (dup names fail)
services.tool_filter.enabled_specs(specs)  # hard-coded until #18
services.tool_call_log.wrap_spec(spec)     # logs every call; sync stays sync, async stays async
adapters.tools.to_structured_tool(spec)    # StructuredTool, args_schema=spec.args_model,
   │                                       # result → adapters.tool_results.result_text
   ▼
apps.agent.get_runtime → build_graph(..., ToolNode(handle_tool_errors=True)) → Runtime.toolsets
apps.agent.run_turn    → on_tool_start / on_tool_end callbacks; idle timer paused while tools run
apps.ui_handlers       → cl.Step(type="tool") per call, open steps closed in finally
```

### Layer responsibilities
- **adapters**: config reading and shape check of `[tools.*]`; toolset provider discovery
  (entry points; no module imports a tool package) and toolset building;
  `ToolSpec` → `StructuredTool`;
  the result-to-string helper (module without `langchain_core`); the three
  `mcp_coder_utils` shims (`redaction`, `tool_spec`, `user_app_data`).
- **services**: tool filter (replaced by #18's resolver), tool-call log (redaction,
  truncation, JSONL writer, `wrap_spec`, public `log_tool_call` for #18's `denied`),
  logging setup (`log_utils` shim; app-log file; `clamp_loggers` for the configured
  providers' packages), `verify` TOOLS rows (shape, provider registered, the provider's own
  `verify` rows). No `langchain_core`.
- **apps**: wiring (`get_runtime` / `close_runtime`), graph error handling, tool callbacks
  and timer pause in `run_turn`, Chainlit tool steps, launcher gate (build + close the
  toolsets once before Chainlit starts).
- **interfaces**: TOOLS section in `verify_formatting`.
- **core**: unchanged.

### Logging strategy (repo-wide from now on)
- All logging goes through `mcp_coder_utils.log_utils` / `mcp_coder_utils.redaction`,
  reached only through local shims. `mcp_coder_utils_isolation` allows exactly four modules:
  `adapters.redaction`, `adapters.tool_spec`, `adapters.user_app_data`,
  `services.logging_setup`.
- `agent-workbench-ui` writes one timestamped app-log file per run in `<app-data>/logs/`
  (default `INFO`, console at `OUTPUT`); `verify` / `prompt` stay console-only.
- The tool-call log (`<app-data>/logs/tool_calls.jsonl`) is the one hand-written exception.

### Key design decisions
| Topic | Decision |
|---|---|
| Tool packages | Plugins: `ToolsetProvider` subclasses found by entry point (`agent_workbench.toolsets`); `[tools.<name>]` = provider name, table passed unchanged |
| Tool config type | No new `core` type; agent-workbench checks only the shape (`tools_config_problems`); keys and paths belong to the provider |
| Validation | Shape rows + "provider registered" + the provider's `verify` rows; `build_toolsets` raises on a shape error, an unregistered provider or a provider build error |
| Module layout | `adapters/toolset_providers.py` discovery (no `langchain_core`); `adapters/tools.py` holds `Toolsets`, `build_toolsets`, `to_structured_tool`; `adapters/tool_results.py` only the result helper (no `langchain_core`) |
| Tests | Fake provider (`tests/adapters/tool_fixtures.py`) patched into `entry_points`; real packages only in `integration` tests, skipped when not installed |
| Wrapper result | `wrap_spec` returns the raw result; size via `len(result_text(result))`; the adapter converts |
| JSONL writes | Open-append-close per write under a `threading.Lock`; no long-lived handle |
| Truncation | One `truncate_text(text, limit)` in `services.tool_call_log`, reused by `ui_handlers` for step output |
| Timer pause | `on_tool_start` → `idle.reschedule(None)`; next `on_chat_model_start` resumes; never depends on a tool-end event |
| Tool steps | Two callbacks (`on_tool_start`, `on_tool_end`); `on_tool_error` events (if emitted) treated as end |

## Files

### Created
| File | Content |
|---|---|
| `src/agent_workbench/adapters/redaction.py` | shim: `token_fingerprint`, `SENSITIVE_KEY_PATTERNS`, `REDACTED_VALUE` |
| `src/agent_workbench/adapters/tool_spec.py` | shim: `ToolSpec`, `ToolCollector` |
| `src/agent_workbench/adapters/user_app_data.py` | shim: `get_user_app_data_dir` |
| `src/agent_workbench/adapters/tool_results.py` | `result_text` |
| `src/agent_workbench/adapters/toolset_providers.py` | `ENTRY_POINT_GROUP`, `registered_providers`, `provider_class`, `provider_packages` |
| `src/agent_workbench/adapters/tools.py` | `Toolsets`, `build_toolsets`, `to_structured_tool` |
| `src/agent_workbench/services/tool_call_log.py` | `truncate_text`, `sanitize_params`, `log_tool_call`, `wrap_spec` |
| `src/agent_workbench/services/tool_filter.py` | `enabled_specs` |
| `tests/conftest.py` | `restore_root_logging` fixture (restores and closes root log handlers) |
| `tests/adapters/test_shims.py` | shim re-exports |
| `tests/adapters/test_tool_results.py` | result conversion |
| `tests/adapters/test_tools.py` | adapter + toolset build |
| `tests/adapters/test_toolset_providers.py` | entry-point discovery |
| `tests/adapters/tool_fixtures.py` | fake provider, `register_providers`, config-file helper |
| `tests/services/test_tool_call_log.py` | log, redaction, truncation, wrapping |
| `tests/services/test_tool_filter.py` | filter |
| `tests/apps/test_agent_tools.py` | agent loop with a fake provider (real providers: `integration`), runtime wiring |
| `tests/test_tool_path_no_mcp.py` | subprocess `sys.modules` test (`integration`, real providers) |

### Modified
| File | Change |
|---|---|
| `pyproject.toml` | extras `[sql]`, `[sql-mssql]`, `[workspace]` as install shortcuts + deptry DEP002 ignore; no `dev` / install-from-github / mypy entry for the tool packages |
| `.importlinter` | `mcp_coder_utils_isolation` tightened; `langchain_model_layer` ignore line; `tool_packages_isolation` (tool packages imported nowhere) |
| `src/agent_workbench/adapters/config.py` | `ConfigFile.tools` / `tools_type_error`; `tools_config_problems` (shape only); shim import |
| `src/agent_workbench/adapters/tool_spec.py` | also re-exports `ToolsetProvider`, `Toolset`, `StaticToolset` |
| `src/agent_workbench/adapters/langchain/_provider_checks.py` | redaction via shim |
| `src/agent_workbench/services/logging_setup.py` | `log_file`, `console_level`, `clamp_loggers` |
| `src/agent_workbench/services/verify.py` | `verify_tools`, report fields, exit code |
| `src/agent_workbench/interfaces/verify_formatting.py` | TOOLS section |
| `src/agent_workbench/apps/agent.py` | `handle_tool_errors`, tool callbacks, timer pause, `Runtime.toolsets`, `build_tools`, `get_runtime` / `close_runtime` |
| `src/agent_workbench/apps/ui_handlers.py` | Chainlit tool steps |
| `src/agent_workbench/apps/ui_launcher.py` | app-log file, default `INFO`, toolset build gate |
| tests of the modified modules | see each step |
| `README.md`, `docs/architecture/architecture.md`, `docs/security/security_design.md` | docs |

`tach.toml`, `core/` – no change.

## Steps
1. mypy overrides for the tool packages (`pyproject.toml`) – *done; reverted in 8*
2. `mcp_coder_utils` shims and tightened import contract – *done*
3. App log for the UI and clamped sibling loggers – *done; clamp reworked in 8 / 10*
4. `[tools]` config reading and validation – *done; key checks removed in 8*
5. Result helper and `ToolSpec` → `StructuredTool` adapter – *done*
6. Tool-call log and `wrap_spec`
7. Tool errors, tool callbacks and inactivity pause in the graph / `run_turn`
8. Remove the hard-coded tool packages (mypy override, `SIBLING_LOGGERS`, `TOOL_KEYS` &
   key checks)
9. Toolset providers: entry-point discovery and `build_toolsets` (plus the extras) –
   **blocked by mcp-coder-utils#61** (provider contract); precondition in the step
10. Runtime wiring, tool filter, logger clamp, agent-loop and `mcp` (integration) tests
11. Chainlit tool steps
12. Launcher gate: build and close the toolsets before Chainlit
13. `verify` TOOLS section with the providers' rows (#27 folded in)
14. Documentation

Steps 6–8 need no sibling change. Steps 9–14 need only the provider contract
(mcp-coder-utils#61); the real providers (mcp-tools-sql#107, mcp-workspace#393) are needed
only for the `integration` tests and the manual smoke test.

Manual smoke test (model lists tables and writes a markdown report) is done by the user
and documented in the PR – not a plan step.
