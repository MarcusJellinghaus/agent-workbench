# agent-workbench Security Design

**Scope**: milestones 1–2 – local, single user, Windows dev machine | **Status**: planned, nothing implemented yet
**Maintainer**: Marcus Jellinghaus

Reporting vulnerabilities: see [`SECURITY.md`](../../SECURITY.md). Architecture: [`docs/architecture/architecture.md`](../architecture/architecture.md).

---

## 1. Key message

The model never gets a database connection or credentials. It can only request a fixed list of configured Python functions, which the app runs and logs. Read-only by default; writes only through named, parameterised update statements the user configures and enables explicitly.

---

## 2. System and trust boundaries

```
                         ┌───────────────────────── developer's Windows machine ─────────────────────────┐
┌──────┐  localhost      │ ┌──────────────────────┐  in-process   ┌────────────────────┐                  │
│ User │────────────────▶│ │ Chainlit UI          │──────────────▶│ mcp-tools-sql      │──▶ SQL Server     │
└──────┘                 │ │ LangGraph agent      │  Python API   │ mcp-workspace      │──▶ workspace dir  │
                         │ │ permission check     │               └────────────────────┘                  │
                         │ └──────────┬───────────┘                                                       │
                         │            │ logs, sessions ──▶ user app-data folder                           │
                         └────────────┼──────────────────────────────────────────────────────────────────┘
                                      │ HTTPS: prompts, tool descriptions, tool results
                                      ▼
                               ┌─────────────┐
                               │ LLM provider│
                               └─────────────┘
```

- **Trusted**: the developer (single user), agent-workbench code, the tool packages, configuration files.
- **Untrusted input**: model output, tool arguments chosen by the model, data content returned by tools (table comments, column values, file contents).
- **Leaves the machine**: everything in the prompt – user messages, system prompt, tool descriptions and tool results – goes to the LLM provider.
- **Identity**: the app runs as the developer. Database access uses Windows authentication with the developer's own rights, which may exceed read-only. The tool configuration, not the database login, is the boundary.

---

## 3. Data sent to the LLM provider

- **Rule**: only providers approved for the classification of the data in use may be configured – e.g. a local model (Ollama) or the company's own endpoint.
- **Minimisation through default permission modes**: schema / table / column read and `validate_sql` are `allow`; profiling tools, `query_*` and update tools are `deny` until the user enables them. Workspace read and write are `allow`.
- Which provider is approved is a policy decision outside this repository.

---

## 4. Controls

### 4.1 Tool permissions

- A mode per tool or tool group in the agent-workbench config: `allow`, `ask` (confirm each call), `ask_session` (confirm once per session), `deny`.
- Unlisted tools are `deny`. `deny` tools are not shown to the model at all.
- `ask` / `ask_session`: Chainlit shows the tool name and its parameters with OK / Cancel before the call runs.
- Defaults in the example config: SQL schema / table / column read, `validate_sql`, workspace read and write → `allow`; everything else → `deny`.

### 4.2 SQL

- Connections and authentication are mcp-tools-sql configuration (`trusted_connection = true`); agent-workbench holds no database credentials.
- No free-SQL tool exists. `validate_sql` only runs EXPLAIN (`SET SHOWPLAN_TEXT ON` on SQL Server) and never executes the statement.
- Profiling tools accept model-written SQL fragments (WHERE clause, query source); mcp-tools-sql checks them with its read-only gates (`validate_where`, `validate_source`).
- Updates only through named, parameterised `updates.*` statements in the mcp-tools-sql config, gated by `allow_updates` and by their permission mode.
- Row limits come from mcp-tools-sql (default 100 rows per result). Today they only truncate the output – all rows are fetched – and there are no query timeouts; both are planned changes in mcp-tools-sql (fetch at most the limit, statement timeout).

### 4.3 Query approval

- The model drafts SQL in the chat or as a workspace file and checks it with `validate_sql`.
- The user adds approved queries to the mcp-tools-sql query config, sets their permission mode and presses Reload.
- Workspace guard: the toolset is not built if the configured workspace contains `~/.agent_workbench/` (config, permissions, logs, sessions) or the mcp-tools-sql config files, so the model can neither approve its own queries nor change its permissions.

### 4.4 Workspace

- Paths are confined to the configured project folder by mcp-workspace (`normalize_path`, which also resolves symlinks); gitignored paths are refused.
- No file-size or file-type limits exist today; `read_file` returns the whole file. A maximum read size is a planned change in mcp-workspace.
- Delete, move and Git / GitHub tools are `deny` by default.

### 4.5 Credentials

- No database password: Windows authentication.
- LLM API keys come from environment variables or the user config, never from the workspace folder.
- Secrets in log lines are redacted (`mcp_coder_utils.redaction`).

### 4.6 Limits

- At most 50 agent steps per turn (LangGraph `recursion_limit`).
- Inactivity timeout per model call.
- Token usage per turn and per session is shown in the UI. No budgets.

### 4.7 Dependencies

- Core dependencies are kept minimal; LLM providers and tool packages are optional extras, imported only when configured.
- Chainlit itself depends on the `mcp` SDK, so it is installed; the tool path never imports it (tested). Making mcp-workspace's Git / GitHub libraries optional is planned but not required; until then they are installed (unused while those tools are `deny`).
- Dependabot and OpenSSF Scorecard run on the repository.

---

## 5. Logging and retention

| Store | Content | Location | Retention |
|---|---|---|---|
| Tool-call log | One line per call: user, tool, parameters, result size, duration. No results. Secrets redacted. | User app-data folder | Until deleted |
| Session database | Full conversations including tool results (LangGraph checkpointer + Chainlit data layer, SQLite) | User app-data folder | Until the user deletes the session in the UI |

Both stores lie outside the workspace folder, so the model cannot read them back through the workspace tools.

---

## 6. Threat model

| # | Risk | Control | Residual risk |
|---|---|---|---|
| 1 | Prompt injection through data (table comments, file contents) makes the model call tools it should not | Permission modes; risky tools (delete, move, Git / GitHub, updates) `deny` by default; `deny` tools not shown | Allowed tools can still be called with model-chosen arguments, e.g. writing misleading files into the workspace |
| 2 | Data leaves the machine through the LLM provider | Approved providers only; data minimisation through default modes | Data returned by allowed tools (schema, file contents) always reaches the provider |
| 3 | Model changes data in the database | No free-SQL tool; updates only through configured `updates.*` statements enabled by the user; `validate_sql` only runs EXPLAIN | An update tool set to `allow` can be called with any parameter values; use `ask` for updates |
| 4 | Model-written SQL fragments in profiling tools | mcp-tools-sql read-only gates; profiling `deny` by default | Depends on the correctness of the mcp-tools-sql gates |
| 5 | Model approves its own queries or permissions | Workspace guard: the toolset is not built if the workspace contains `~/.agent_workbench/` or the mcp-tools-sql config files; `verify` reports it | – |
| 6 | Path traversal out of the workspace | `normalize_path` in mcp-workspace (rejects `..`, resolves symlinks) | If path resolution fails, the containment check is skipped (documented gap in mcp-workspace) |
| 7 | Credentials leak (database, LLM API key) | Windows authentication; API key from environment / user config; log redaction | Secrets stored in the data itself can reach the provider through tool results |
| 8 | Expensive or long-running queries, huge files | Step limit per turn; output row limits; planned: statement timeout and fetch limit in mcp-tools-sql, maximum read size in mcp-workspace | Until those land, a slow query blocks the turn and a large file goes to the provider in full |
| 9 | Sensitive data in logs and sessions | Tool-call log without results; stores in the user app-data folder, which the workspace guard keeps out of the workspace | Sessions with data are kept without time limit, protected only by the user profile |
| 10 | Compromised dependency | Minimal core, optional extras, pinned minimum versions, Dependabot, Scorecard | The LangChain / Chainlit ecosystem is large |

---

## 7. Out of scope (M1–M2)

Multi-user operation, real login / user management (M1 at most maps every request to the OS user), shared server deployment, a separate data API, AD / Entra identity and user delegation. They are future ideas, not planned in detail.
