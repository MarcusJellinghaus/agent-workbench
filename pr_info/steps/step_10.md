# Step 10 – Docs

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 10: update README,
`docs/architecture/architecture.md` and `docs/security/security_design.md` for the chat UI.
No code changes; all checks pass; one commit.

## WHERE
- Modify `README.md`, `docs/architecture/architecture.md`, `docs/security/security_design.md`

## WHAT / HOW
### README
- Status line: chat UI added.
- Setup: Python 3.11–3.13 supported (Chainlit requires < 3.14).
- New section `agent-workbench-ui`:
  - starts with the dependency check (`langgraph`, `langchain_core` →
    `pip install "agent-workbench[langchain]"`) and the full `verify` (incl. the test
    prompt); on failure prints the verify report and exits 1;
  - serves on `http://127.0.0.1:8000` only (`CHAINLIT_PORT` changes the port; `CHAINLIT_HOST`
    is forced to `127.0.0.1`); opens the browser;
  - Chainlit's files (`.chainlit/config.toml`, rewritten on every start, `.files/`) live in
    `%USERPROFILE%\.agent_workbench\chainlit`; no `.env` file is read; listed Chainlit env vars
    (database, Literal AI, Slack / Discord / Teams, custom auth, root path, SSL) are ignored
    with a warning;
  - limits: 50 steps per turn, 300 s without a stream event, 3600 s per turn; token usage
    after each answer; Stop button.
  - `--log-level`.

### `docs/architecture/architecture.md`
- §5 table: `apps` status → "LangGraph agent (no tools), Chainlit chat page,
  `agent-workbench-ui`"; the core-dependencies line: `chainlit` core, `langgraph` in
  `[langchain-base]` (as mcp_coder), session-store packages still #16.
- §6 "Limits (planned)" → "Limits": 50 steps (`recursion_limit`, `GraphRecursionError` shown
  as a message), 300 s inactivity per turn (no stream event), 3600 s overall per turn, chat
  model HTTP timeout 300 s, token usage per turn and per session; no budgets.

### `docs/security/security_design.md`
- §2: the UI binds to `127.0.0.1` only (host forced); origin check on HTTP and WebSocket
  (Chainlit's Socket.IO origin check is off; `allow_origins` covers CORS only).
- §4.5: Chainlit reads no `.env` (env file pointed at a never-created file in the app
  root); credentials / integration env vars removed before Chainlit is imported.
- §4.6: limits wording as in architecture §6.
- §4.7: Chainlit depends on the `mcp` SDK; the MCP feature is off in the generated config
  and the app uses no MCP.
- §5: Chainlit's app root (`.chainlit/`, `.files/`) in the user app-data folder; no
  database / Literal AI data layer (env vars removed); sessions only in memory until #16.
- Status line: "partly implemented (chat UI)".

## Checks / commit
pylint, pytest, mypy (no code change, sanity only), file-size check. Ensure `.scratch/`
does not exist. Commit: `docs: chat UI, limits and Chainlit isolation`.
