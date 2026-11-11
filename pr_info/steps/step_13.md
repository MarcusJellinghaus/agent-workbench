# Step 13 – Documentation

## LLM prompt
Read `pr_info/steps/summary.md`, this file (`pr_info/steps/step_13.md`) and the "Docs"
bullets of issue #17 (`github_issue_view(17)`), then update the three documents. Keep the
existing style: short sentences, no filler. Docs only; run pytest
(`-n auto -m "not integration"`) to confirm nothing broke. One commit.

## WHERE
- `README.md`
- `docs/architecture/architecture.md`
- `docs/security/security_design.md`

## WHAT

### README.md
- Status line and `agent-workbench-ui` intro: drop "no tools yet"; name the default tools
  (SQL schema tools and `validate_sql`, workspace read / write).
- Setup: extras `[sql]`, `[sql-mssql]` (SQL Server driver), `[workspace]`.
- Configuration: example
  ```toml
  [tools.sql]
  query_config = "C:/Users/me/.mcp-tools-sql/queries.toml"   # mcp-tools-sql query config
  # database_config = "..."                                  # optional; package default
  [tools.workspace]
  project_dir = "C:/Users/me/work/reports"
  ```
  Absolute paths only (`~` allowed); no `[tools]` table → no tools; unknown keys warn.
  "Keep the mcp-tools-sql query config outside the workspace – the model can write
  files there."
- `verify`: "Sections:" line gains TOOLS; exit-code line: also 1 on a TOOLS error.
- `agent-workbench-ui`: "Start:" bullet – after `verify`, the configured toolsets are built
  once and closed; a build error stops the start. "Limits per turn" bullet – the 300 s
  inactivity timer pauses while tools run; 3600 s overall still applies. `--log-level`
  bullet – default `INFO`; app log `%USERPROFILE%\.agent_workbench\logs\agent_workbench_ui_<timestamp>.log`,
  console at `OUTPUT`. Tool-call log `logs\tool_calls.jsonl`. Tool calls appear as steps
  with arguments and a truncated result.

### docs/architecture/architecture.md
- §3: "Configuration … and the user app-data folder lie outside the workspace folder" →
  "by configuration, not enforced – known gap".
- §5 building-block table: `services` – tool filter, tool-call logging (no toolset
  building); `adapters` – toolset building (called from `apps`), spec → LangChain tool,
  lazy loading, `mcp_coder_utils` shims; Status column updated (tools in the agent).
- §5 per-layer table: `services` reaches `mcp-coder-utils` only via `logging_setup`;
  redaction / tool contract / app-data dir via the `adapters` shims.
- §6 "Logging and retention": logging strategy (all logging via `log_utils` /
  `redaction` through shims; `mcp_coder_utils_isolation` lists the four shim modules;
  UI-only app-log file per run; `mcp_workspace` / `mcp_tools_sql` loggers clamped to
  `INFO` because their DEBUG logs parameters and results unredacted – their INFO / ERROR
  lines still contain file paths and error texts); the tool-call log as the one
  hand-written JSONL exception (fields, 200-char truncation, key-substring redaction,
  over-redaction accepted, secrets in free text not detected, calls failing before `fn`
  runs not logged until #18, errors returned as text log as `ok`).
- §6 "Limits": inactivity wording – 300 s without a stream event, paused while tools run.

### docs/security/security_design.md
- §4.3 workspace-guard bullet and threat rows 5 and 9 → "Workspace guard: planned in
  mcp-workspace, not implemented – known gap"; row 5 drops "`verify` reports it". Add the
  query-config gap: an mcp-tools-sql query config inside the workspace (e.g. a
  `pyproject.toml` with `[tool.mcp-tools-sql]`) is writable by the model.
- §5 "Both stores lie outside the workspace folder" → "by configuration, not enforced –
  known gap".
- §4.5: secrets in tool-call log lines are redacted by the `services` redactor (recursive,
  case-insensitive key substrings of `SENSITIVE_KEY_PATTERNS`).
- §4.6: inactivity wording as in architecture §6.
- §5 retention table: rows for the app log (`<app-data>/logs/agent_workbench_ui_*.log`)
  and `tool_calls.jsonl` – no retention (kept until deleted); may contain parameter data.
  Tool steps (arguments, truncated results) are persisted in `chainlit.sqlite`.
- `handle_tool_errors=True` sends the exception text of a failed tool to the provider
  (§3 data sent to the provider).
- Link "Logging and retention" in `architecture.md` §6 from §5.

## HOW / ALGORITHM / DATA
n/a – documentation only.
