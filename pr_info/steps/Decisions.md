# Decisions – #17 plan revision (plugin model), 2026-11-11

Logged from the discussion after the Step 6 block (`mcp_tools_sql.toolset` not installed).

| # | Decision | Discussed |
|---|---|---|
| 1 | Tool packages are plugins: agent-workbench finds a `ToolsetProvider` by entry point (`agent_workbench.toolsets`) and passes it the `[tools.<name>]` table unchanged. It names no tool package in its code and checks no tool config keys. | Marcus questioned why mcp-tools-sql must be installed ("This should be a flexible application with an add-in model"); approved drafting the plugin model ("Yes!!!!") and the issue updates ("Okay, do it"). |
| 2 | Follow mcp_coder's toolkit plugin pattern (consumer-named entry-point group, base class that only stores its config, `verify` returning `VerifyItem` rows), but with its own contract in mcp-coder-utils (#61, rewritten). `Toolkit` itself is not reused, because it runs fixed actions and returns findings. | Marcus asked whether mcp_coder's plugin model could be used; answer (share the pattern and `VerifyItem`, separate contract) accepted with "Yes" / "Okay, do it". |
| 3 | Tool packages are not in `dev` and not needed for unit tests: a fake provider is patched into `entry_points`; real packages appear only in `integration` tests, which skip when not installed. Extras `[sql]`, `[sql-mssql]`, `[workspace]` stay as install shortcuts (DEP002 ignore). No `install-from-github` entry for mcp-tools-sql. | Follows from Marcus's "Why does it need to be installed?"; part of the approved drafts. |
| 4 | Code on the branch that hard-codes the two packages (mypy override, `SIBLING_LOGGERS`, `TOOL_KEYS` / `REQUIRED_TOOL_KEYS` / `tool_path` and key checks) is removed (new step 8). | Marcus asked "Is there some obsolete code that we do not need anymore?"; removal list approved ("Yes", "Okay, do it"). |
| 5 | #27 is folded into #17: `verify` renders the providers' `verify(connect=...)` rows; `agent-workbench verify` passes `connect=True`, the UI gate `connect=False`. | Proposed in the drafts; approved with "Okay, do it". |
| 6 | Order: tool-call log and graph/timer steps first (no sibling needed), then the removal step, then discovery and the rest (blocked by mcp-coder-utils#61). | Proposed in the drafts; approved with "Okay, do it". |

Open (epic #13, not decided here): location of #18's permission config – proposal is a top-level `[permissions]` table.
