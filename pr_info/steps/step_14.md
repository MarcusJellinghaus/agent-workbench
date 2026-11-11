# Step 14 – Documentation

## LLM prompt
Read `pr_info/steps/summary.md`, this file (`pr_info/steps/step_14.md`) and the "Docs"
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
- Setup: tool packages are plugins. Extras `[sql]`, `[sql-mssql]` (SQL Server driver),
  `[workspace]` are install shortcuts for the two current packages; any installed package
  that registers an `agent_workbench.toolsets` entry point works the same way.
- Configuration: `[tools.<name>]` = provider name; the table goes to that provider
  unchanged. Example
  ```toml
  [tools.sql]                 # provider "sql" (mcp-tools-sql)
  query_config = "C:/Users/me/.mcp-tools-sql/queries.toml"
  # database_config = "..."   # optional; package default
  [tools.workspace]           # provider "workspace" (mcp-workspace)
  project_dir = "C:/Users/me/work/reports"
  ```
  No `[tools]` table → no tools. Keys and path rules belong to the provider (both current
  providers require absolute paths, `~` allowed; unknown keys warn) – `verify` shows its
  rows. Adding a package: install it, add its table. Writing one: mcp-coder-utils README
  (toolset provider contract).
  "Keep the mcp-tools-sql query config outside the workspace – the model can write
  files there."
- `verify`: "Sections:" line gains TOOLS (the providers' own checks; `verify` may connect,
  the UI start doesn't); exit-code line: also 1 on a TOOLS error.
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
  building); `adapters` – toolset provider discovery (entry points
  `agent_workbench.toolsets`; no tool package imported anywhere), toolset building
  (called from `apps`), spec → LangChain tool, `mcp_coder_utils` shims; Status column
  updated (tools in the agent).
- §5 per-layer table: `services` reaches `mcp-coder-utils` only via `logging_setup`;
  redaction / tool contract / app-data dir via the `adapters` shims.
- §6 "Logging and retention": logging strategy (all logging via `log_utils` /
  `redaction` through shims; `mcp_coder_utils_isolation` lists the four shim modules;
  UI-only app-log file per run; the configured providers' package loggers clamped to
  `INFO` because the current packages' DEBUG logs parameters and results unredacted –
  their INFO / ERROR lines still contain file paths and error texts); the tool-call log as the one
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
- Plugin trust: any installed package registering an `agent_workbench.toolsets` entry
  point can supply tools once its `[tools.<name>]` table is configured – trust = what the
  user installs and configures.

## HOW / ALGORITHM / DATA
n/a – documentation only.
