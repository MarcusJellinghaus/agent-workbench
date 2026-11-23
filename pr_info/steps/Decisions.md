# Decisions

## Step 5 integration gate (2026-11-23, after the executor run blocked on step 5)

- The integration run of `tests/test_tool_path_no_mcp.py` counts as done when it is
  skipped because `sql` / `workspace` are not registered in the
  `agent_workbench.toolsets` entry-point group. Neither provider registers yet
  (mcp-workspace #393, mcp-tools-sql #107), so the test skips in every environment.
  The run is recorded as deferred until those land.
- `mcp-tools-sql` and `mcp-workspace` stay optional extras (`sql`, `sql-mssql`,
  `workspace`); they do not become hard dependencies of agent-workbench.
