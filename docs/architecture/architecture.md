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

- Python 3.11+.
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
(logs, session database) lie outside the workspace folder.

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
| apps | `agent_workbench.apps` | LangGraph agent, Chainlit UI, batch runner (M2) | empty |
| interfaces | `agent_workbench.interfaces` | CLI (`verify`) | CLI placeholder |
| services | `agent_workbench.services` | Permission check and confirmation, tool-call logging, toolset building and reload | empty |
| adapters | `agent_workbench.adapters` | Copied LLM model layer, tool-spec → LangChain tool adapter, lazy loading of tool packages | empty |
| core | `agent_workbench.core` | Config models, permission modes, domain types | `greeting.py` placeholder |

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
| adapters | `langchain-core`, LangChain provider packages (optional), `httpx`, `truststore`, mcp-tools-sql and mcp-workspace (optional, lazy), `mcp-coder-utils` |
| services | `mcp-coder-utils` (redaction, logging) |
| interfaces | none beyond the standard library |
| apps | `langgraph`, `langchain-core`, `chainlit` |

Core dependencies: `pydantic`, `chainlit`, `langgraph`, `langchain-core`, `httpx`,
`truststore`, `mcp-coder-utils`, plus the session-store packages (SQLite checkpointer,
Chainlit data layer). Everything else is an extra: LLM providers named as in mcp_coder
(`[langchain-openai]`, `[langchain-anthropic]`, `[langchain-gemini]`, `[langchain-ollama]`,
meta extra `[langchain]`) and tools (`[sql]`, `[sql-mssql]`, `[workspace]`).

### Placeholder code

`core/greeting.py` and `interfaces/cli.py` (entry point `agent-workbench`) exist only
to exercise the toolchain. Remove them when real code lands.

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

### Logging and retention (planned)

One structured line per tool call: user, tool, parameters, result size, duration; no
results; secrets redacted. Sessions keep full conversations until the user deletes them.
Logs and the session database live in the user app-data folder.

### Limits (planned)

As in mcp_coder: at most 50 agent steps per turn (LangGraph `recursion_limit`), an
inactivity timeout per model call, token usage per turn and per session shown in the UI.

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
