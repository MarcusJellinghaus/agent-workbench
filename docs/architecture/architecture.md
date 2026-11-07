# agent-workspace Architecture

**Framework**: Arc42 (condensed) | **Version**: 0.1 | **Status**: Skeleton — milestone 1 not started
**Maintainer**: Marcus Jellinghaus

> This document is a starting point derived from the project concept. Sections marked
> *planned* describe intent, not code. Update it as each milestone lands.

---

## 1. Introduction & Goals

### Purpose

A small, governed web LLM client. The model reaches company data only through a fixed,
vetted set of Python operations (later an internal API), with server-side permission
checks and full audit logging.

### Key Quality Goals

- **Governance**: the LLM never touches a database or file share directly; it can only
  request allow-listed operations.
- **Least privilege**: tools the user may not use are never shown to the model; every
  call is re-checked on the server side.
- **Auditability**: every tool call is logged with user, operation, parameters, result
  size and duration, joined to the LLM-layer log by one request ID.
- **Reviewability**: a small codebase Security can read end to end.

### Design Principles

- **The design, not the protocol, is the security boundary.** One vetted service,
  managed credentials, server-side permission checks, logging. The same operation core
  can be exposed as plain Python, REST, or MCP later.
- **Read-only by default.** Writes only through admin-configured operations with human
  confirmation (milestone 5).
- **Bounded output.** Row limits and timeouts on every data operation.
- **Swappable identity.** Connection handling is abstracted so user delegation
  (Kerberos) can be added without redesign.

### Stakeholders

- **Analysts**: explore metadata, analyse data, write reports, run batch jobs.
- **Security**: reviews the data service and permission model.
- **Admins** (milestone 4+): manage permissions and approve queries.

---

## 2. Architecture Constraints

- Python 3.11+
- Milestones 1–2 run on a Windows dev machine as the developer (Windows authentication
  to SQL Server via pyodbc + ODBC Driver 18). The developer's rights may exceed
  read-only, so tools must be read-only in code.
- Any LangChain-supported LLM provider; none is fixed.
- Developed with mcp-coder workflows (see `.claude/`, `pyproject.toml`).

---

## 3. Context & Scope

```
┌────────┐  browser  ┌──────────────────────────┐  plain Python (M1)  ┌──────────────────┐
│  User  │──────────▶│  Chat UI (Chainlit)      │  REST (M3+)         │  Operations      │
└────────┘           │  Agent (LangGraph)       │────────────────────▶│  (SQL, Workspace)│
                     └───────────┬──────────────┘                     └────────┬─────────┘
                                 │ LangChain                                   │
                                 ▼                                             ▼
                          ┌─────────────┐                            ┌──────────────────┐
                          │ LLM provider│                            │ SQL Server, files│
                          └─────────────┘                            └──────────────────┘
```

---

## 4. Solution Strategy

| Component | Technology | Milestone |
|---|---|---|
| Chat UI | Chainlit (tool calls visible, session history) | 1 |
| LLM orchestration | LangGraph + LangChain chat models; provider config from mcp-coder | 1 |
| Tools | Functions from the SQL and Workspace MCP packages, registered as LangGraph tools | 1 |
| Sessions | LangGraph checkpointer + Chainlit data layer on SQLite | 1 |
| Data API | FastAPI with an operation registry; the only holder of credentials | 3 |
| Admin GUI | NiceGUI or FastAPI + React | 4 |

Milestone 1 is one app; the tool code lives in its own layer so it can be split into
the data API later.

### How a tool call works

1. The app gives the model each permitted tool's name, description and JSON schema.
2. The model replies with a structured request, e.g. `read_columns(table="Customers")`.
3. LangGraph runs the matching function — locally in M1, over HTTP with user token and
   request ID from M3.
4. The function checks permissions, runs, logs, returns JSON.
5. The result goes back to the model.

---

## 5. Building Block View

Package: `src/agent_workspace/`. Dependencies flow downward only; enforced by
`.importlinter` and `tach.toml`.

| Layer | Package | Responsibility | Status |
|---|---|---|---|
| apps | `agent_workspace.apps` | LangGraph agent, Chainlit UI, batch runner | empty |
| interfaces | `agent_workspace.interfaces` | CLI (`cli.py`), later the FastAPI data API | CLI placeholder |
| services | `agent_workspace.services` | Permission checks, audit logging, query approval | empty |
| adapters | `agent_workspace.adapters` | SQL Server, file system, auth | empty |
| core | `agent_workspace.core` | Permission model, config, domain types | `greeting.py` placeholder |

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
| adapters | `pyodbc`, SQL and Workspace MCP packages (tool functions), `smbprotocol`, auth / Kerberos libraries |
| services | none of its own; uses core and adapters (permission-checking wrappers, audit) |
| interfaces | `fastapi`, `uvicorn` (milestone 3) |
| apps | `langchain-*`, `langgraph`, `chainlit`, `nicegui` |

### Placeholder code

`core/greeting.py` and `interfaces/cli.py` (entry point `agent-workspace`) exist only
to exercise the toolchain. Remove them when real code lands.

---

## 6. Cross-cutting Concepts

### Permission model (planned)

Levels per data source, schema and table:

1. Schema only — schemas, tables, columns, types.
2. Column statistics and sample/distinct values — allowed columns only.
3. Read data — approved tables, with row limits.
4. Named queries — admin-approved, parameterised; the model only fills in parameters.
5. Approved writes — configured updates, with human confirmation.

Rules = operation + scope + level, assigned to roles (mapped to AD groups from M4), plus
individual overrides. Read-only database roles back up the app-level rules.

### Query approval (planned)

- M1: a propose-query tool writes drafts to a drafts folder; the user copies approved
  ones into the approved-queries file; the app reloads it and turns each entry into a
  tool. The model never writes to the approved file.
- M4: review list in the admin GUI with who/when and optional four-eyes approval.

### Workspace confinement (planned)

Workspace tools resolve paths and stay inside the configured project folder; allowed
file types and size limits; no delete in M1.

### Logging (planned)

Two layers joined by one request ID: the LLM layer logs user, prompt, model and tools
chosen; the data layer logs user, operation, parameters, rows and duration.

---

## 7. Roadmap

1. Basic app on a Windows dev machine — chat, agent, read-only SQL metadata tools,
   workspace folder, sessions, tool-call logging, file-based query approval.
2. Sequential batch processing — repeat loop with stop checks; LEI lookup first.
3. Separate data API — FastAPI with operation registry.
4. Governance and identity — admin GUI, AD roles, Entra login, OpenShift, secrets.
5. Writes and user delegation — approved updates, Kerberos delegation, file shares.
6. Parallel batches — templates, job runner, concurrency limits, retries.
7. Extensions — Workspace and Python plugins in a sandbox, Postgres, MCP option.

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
