# agent-workbench Architecture

**Framework**: Arc42 (condensed) | **Version**: 0.2 | **Status**: Skeleton — milestone 1 planned
**Maintainer**: Marcus Jellinghaus

> Sections marked *planned* describe intent, not code. Update this document as each
> epic lands. Security controls and the threat model: [`docs/security/security_design.md`](../security/security_design.md).

---

## 1. Introduction & Goals

### Purpose

A small, governed web LLM client that runs locally on a Windows dev machine. The model
reaches company data only through configured tools from existing Python packages
(mcp-tools-sql, mcp-workspace), used through their Python API – no MCP. A permission
mode per tool decides what the model may call; every tool call is logged.

### Key Quality Goals

- **Governance**: the model never gets a database connection or credentials; it can only
  request configured tools.
- **Least privilege by configuration**: a permission mode per tool (`allow`, `ask`,
  `ask_session`, `deny`); unlisted tools are `deny` and are not shown to the model.
- **Auditability**: every tool call is logged with user, tool, parameters, result size
  and duration.
- **Reviewability**: a small codebase and a minimal set of core dependencies.

### Design Principles

- **The design, not the protocol, is the security boundary.** Vetted tools, permission
  modes and logging – the same tool definitions serve MCP servers and this app.
- **Configuration decides, read-only by default.** Writes only through named, parameterised
  update statements the user configures and enables.
- **Bounded.** A step limit per turn; row limits on data tools. Query timeouts, fetch limits and a maximum file read size are planned changes in the tool packages.
- **Configured optionals.** LLM providers and tool packages are optional extras, imported
  only when configured.
- **Reuse, don't rebuild.** agent-workbench defines no tools of its own (except batch
  control in M2); it copies the LangChain model layer from mcp_coder.
- **Follow mcp_coder.** Where possible and sensible, structure, naming, config, extras and
  `verify` follow mcp_coder.

### Stakeholders

- **Users** (developer / analyst): explore metadata, analyse data, write reports, run batch jobs.
- **Security**: reviews the security design.

---

## 2. Architecture Constraints

- Python 3.11–3.13 (Chainlit requires < 3.14).
- Milestones 1–2 run locally on a Windows dev machine, single user, as the developer.
  Database access uses the developer's Windows identity, whose rights may exceed
  read-only – the tool configuration, not the login, is the boundary.
- Any LangChain-supported LLM provider; none is fixed.
- Developed with mcp-coder workflows (see `.claude/`, `pyproject.toml`).

---

## 3. Context & Scope

```
┌────────┐ localhost ┌──────────────────────────┐ in-process, Python API ┌────────────────┐
│  User  │──────────▶│ Chat UI (Chainlit)       │───────────────────────▶│ mcp-tools-sql  │──▶ SQL Server
└────────┘           │ Agent (LangGraph)        │                        │ mcp-workspace  │──▶ workspace folder
                     │ Permission check, logging│                        └────────────────┘
                     └───────────┬──────────────┘
                                 │ LangChain (copied model layer)
                                 ▼
                          ┌─────────────┐
                          │ LLM provider│
                          └─────────────┘
```

Configuration (agent-workbench config, mcp-tools-sql config) and the user app-data folder
(logs, session database) lie outside the workspace folder by configuration, not enforced –
known gap (workspace guard planned in mcp-workspace).

---

## 4. Solution Strategy

| Component | Technology | Epic |
|---|---|---|
| Chat UI | Chainlit: tool calls visible, session history, Reload button, confirmation dialog | M1 – Working chat UI |
| LLM orchestration | LangGraph + LangChain chat models; model layer copied from mcp_coder (after a light refactor there) | M1 – Working chat UI |
| Sessions | LangGraph checkpointer + Chainlit data layer on SQLite | M1 – Working chat UI |
| `verify` command | Config and LLM provider checks; extended with tool and permission checks | M1 – both epics |
| Tools | Tool specs (`ToolSpec`, contract in mcp-coder-utils) exported by mcp-tools-sql and mcp-workspace, turned into LangChain tools | M1 – Tools without MCP |
| Tool permissions | Mode per tool / group; confirmation dialog | M1 – Tools without MCP |
| Batch runs | Sequential repeat loop with stop checks | M2 |

### How a tool call works

1. The app gives the model the name, description and JSON schema of every tool whose
   mode is not `deny`.
2. The model replies with a structured request, e.g. `read_columns(table="Customers")`.
3. The permission check applies the tool's mode; for `ask` / `ask_session` the user
   confirms in Chainlit.
4. The arguments are validated, the function runs in-process, the call is logged.
5. The result goes back to the model, which answers or calls another tool.

---

## 5. Building Block View

Package: `src/agent_workbench/`. Dependencies flow downward only; enforced by
`.importlinter` and `tach.toml`.

| Layer | Package | Responsibility (planned) | Status |
|---|---|---|---|
| apps | `agent_workbench.apps` | LangGraph agent, Chainlit UI, batch runner (M2) | LangGraph agent with tools (wiring, tool errors, tool callbacks), Chainlit chat page with tool steps, `agent-workbench-ui` (toolset build gate), sessions (save, list, resume, delete) |
| interfaces | `agent_workbench.interfaces` | CLI (`verify`) | CLI: verify (incl. TOOLS), prompt |
| services | `agent_workbench.services` | Permission check and confirmation, tool filter, tool-call logging | verify checks, logging setup, tool filter (hard-coded until permissions), tool-call log |
| adapters | `agent_workbench.adapters` | Copied LLM model layer, toolset provider discovery (entry points `agent_workbench.toolsets`; no tool package imported anywhere), toolset building (called from `apps`), tool-spec → LangChain tool adapter, `mcp_coder_utils` shims | copied LLM model layer, config loader, chat-model functions, provider discovery, toolset building, tool adapter, shims |
| core | `agent_workbench.core` | Config models, permission modes, domain types | `LLMConfig` |

Additional contracts:

- `core` imports no other layer.
- Source never imports `tests`.

### Third-party dependencies per layer

Each runtime dependency may be imported only by the layer(s) listed. The issue that
adds a dependency also adds its import-linter `forbidden` contract
(`include_external_packages = True` is already set).

| Layer | Allowed third-party libraries |
|---|---|
| core | `pydantic` only (models, config); `pydantic` is allowed in every layer |
| adapters | `langchain-core`, LangChain provider packages (optional), `httpx`, `truststore`, `mcp-coder-utils` (only in the shims `redaction`, `tool_spec`, `user_app_data`); tool packages are never imported, only loaded through their entry points |
| services | `mcp-coder-utils` only via `logging_setup` (`log_utils`); redaction, tool contract and app-data dir via the `adapters` shims |
| interfaces | none beyond the standard library |
| apps | `langgraph`, `langchain-core`, `chainlit`, `sqlalchemy`, `aiosqlite` |

Core dependencies: `chainlit`, `truststore`, `mcp-coder-utils`, and for Chainlit's data
layer `sqlalchemy[asyncio]`, `aiosqlite` and `aiohttp` (`aiohttp` is imported only by
Chainlit, so it has no contract). `langchain-core`, `langgraph`, the SQLite checkpointer
(`langgraph-checkpoint-sqlite`) and `httpx` are in `[langchain-base]`, as in mcp_coder.
Everything else is an extra: LLM providers named as in mcp_coder (`[langchain-openai]`,
`[langchain-anthropic]`, `[langchain-gemini]`, `[langchain-ollama]`, meta extra
`[langchain]` for all four) and tools (`[sql]`, `[sql-mssql]`, `[workspace]`; install
shortcuts only – any package registering an `agent_workbench.toolsets` entry point is a
tool plugin).

### Placeholder code

The toolchain placeholder (`core/greeting.py`, the greeting CLI) was removed in #14.

---

## 6. Cross-cutting Concepts

### Tool permissions (planned)

A mode per tool or tool group in the agent-workbench config: `allow` (runs without
asking), `ask` (user confirms each call), `ask_session` (user confirms once per session),
`deny` (not shown to the model; default for unlisted tools). Example defaults: SQL schema /
table / column read, `validate_sql`, workspace read and write → `allow`; everything else →
`deny`. Later: rules on tool arguments (e.g. per schema).

### Query approval (planned)

The model drafts SQL in the chat or as a workspace file and checks it with
`validate_sql`. The user adds approved queries to the mcp-tools-sql query config (outside
the workspace folder), sets their permission mode and presses Reload; each query becomes a
`query_*` tool.

### Workspace confinement (planned)

mcp-workspace confines paths to the configured project folder. Delete, move and
Git / GitHub tools are `deny` by default.

### Logging and retention

Logging strategy:

- All logging goes through `mcp_coder_utils.log_utils` / `mcp_coder_utils.redaction`,
  reached only through local shims. The import-linter contract `mcp_coder_utils_isolation`
  allows exactly four modules to import `mcp_coder_utils`: `adapters.redaction`,
  `adapters.tool_spec`, `adapters.user_app_data` and `services.logging_setup`.
- App log: only `agent-workbench-ui` writes a file – one per run,
  `<app-data>/logs/agent_workbench_ui_<timestamp>.log`, level from `--log-level` (default
  `INFO`), console at `OUTPUT`. `verify` and `prompt` log to the console only.
- The loggers of the configured providers' top-level packages are clamped to `INFO`: at
  DEBUG the current tool packages log parameters and results unredacted. Their `INFO` /
  `ERROR` lines still contain file paths and error texts.

Tool-call log: the one hand-written exception, since `log_utils` configures only the root
logger and cannot write a separate file independent of `--log-level`.

- One JSON line per call in `<app-data>/logs/tool_calls.jsonl`: UTC timestamp, OS user,
  tool, parameters, outcome (`ok` / `error` / `cancelled`), result size (length of the
  text the model receives), duration. Never the result.
- Parameters: strings longer than 200 characters are cut and their full length noted, also
  inside nested dicts / lists. Keys containing one of `SENSITIVE_KEY_PATTERNS`
  (case-insensitive substring, recursive) are replaced by `REDACTED_VALUE`. Over-redaction
  (e.g. `max_tokens`) is accepted; secrets inside free text (SQL literals, file content)
  are not detected.
- Not logged: calls that fail before the tool function runs (invalid arguments, unknown
  tool name) – until the permission node (#18) logs them. Errors a tool returns as text
  log as `ok`.
- A failed write is logged to the app log and does not abort the turn.

Sessions: full conversations are kept until the user deletes them. Two SQLite files in
`<app-data>/sessions/` (WAL mode): `checkpoints.sqlite` (LangGraph `AsyncSqliteSaver`, the
model's state) and `chainlit.sqlite` (Chainlit data layer, what the page shows). A delete
removes the thread from both, with `secure_delete` and a WAL checkpoint; details in the
security design, §5.

### Limits

As in mcp_coder:

- At most 50 agent steps per turn (LangGraph `recursion_limit`); a `GraphRecursionError`
  is shown as a message.
- 300 s inactivity per turn (no stream event), paused while tools run, and 3600 s overall
  per turn.
- Chat model HTTP timeout 300 s.
- Token usage per turn and per session shown in the UI. No budgets.

---

## 7. Roadmap

1. **Basic app on a Windows dev machine** – epics "Working chat UI" and "Tools without MCP".
2. **Sequential batch processing** – repeat loop with stop checks; LEI lookup first.

Future ideas, not planned in detail: parameter-level permissions, a separate data API,
governance and identity (AD / Entra, OpenShift), writes with user delegation, parallel
batches, further tool packages (e.g. Python in a sandbox).

---

## 8. Quality Tooling

| Check | Tool | Where |
|---|---|---|
| Lint / format | ruff (`ruff check`, `ruff format`) | CI push |
| Types | mypy `--strict` | CI push |
| Static errors | pylint | CI PR |
| Tests | pytest (+ xdist, coverage) | CI push and PR |
| Layering | import-linter, tach | CI push / PR |
| Dead code | vulture | CI push |
| Dependency hygiene | deptry, `tools/check_no_url_deps.py` | CI PR / push |
| File size | `mcp-coder check file-size` (750 lines) | CI push |

Test approach: the agent loop is tested with a scripted fake chat model (permissions,
confirmation, logging, Reload); SQL against an SQLite target; real-LLM tests are marked
`integration` and run locally only; the Chainlit UI gets a manual smoke test per epic.
