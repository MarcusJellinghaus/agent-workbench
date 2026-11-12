# agent-workbench

Governed LLM chat workbench: configurable tool access, per-user permissions and audit logging.

Status: LLM core (config, `verify`, `prompt`) and a chat UI (`agent-workbench-ui`, with
saved sessions and tools: SQL schema tools and `validate_sql`, workspace read / write). See
[docs/architecture/architecture.md](docs/architecture/architecture.md) for the design and
roadmap.

## Setup on Windows

Requires Python 3.11–3.13 (Chainlit does not support 3.14 yet).

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[langchain]"
```

`[langchain]` installs all providers. For one provider only, use its extra instead:
`".[langchain-openai]"`, `".[langchain-anthropic]"`, `".[langchain-gemini]"` or
`".[langchain-ollama]"`.

Tool packages are plugins. Extras for the two current ones: `[sql]` (mcp-tools-sql),
`[sql-mssql]` (with the SQL Server driver) and `[workspace]` (mcp-workspace), e.g.
`pip install -e ".[langchain,sql-mssql,workspace]"`. They are install shortcuts only: any
installed package that registers an `agent_workbench.toolsets` entry point works the same
way.

### Development setup

Requires [uv](https://docs.astral.sh/uv/).

```bat
tools\reinstall_local.bat
```

This creates `.venv`, installs the package in editable mode with the `dev` extra
(pytest, mypy, pylint, ruff, import-linter, tach, vulture, deptry, mcp-coder and its MCP
servers) and activates the venv. On Linux/macOS: `source tools/reinstall_local.sh`.

## Configuration

Config file: `%USERPROFILE%\.agent_workbench\config.toml`

```toml
[llm]
backend = "openai"        # openai | gemini | anthropic | ollama
model = "gpt-4o-mini"
# api_key = "..."         # prefer the vendor env var (OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY)
# base_url = "https://host/v1"
# api_version = "..."     # Azure OpenAI only
```

Precedence per key:

1. `AGENT_WORKBENCH_LLM_BACKEND`, `AGENT_WORKBENCH_LLM_MODEL`, `AGENT_WORKBENCH_LLM_BASE_URL`,
   `AGENT_WORKBENCH_LLM_API_VERSION` (an empty value counts as unset)
2. `[llm]` in `config.toml`
3. unset

For the API key, the vendor env var beats `api_key`. Nothing is read from a workspace folder.

### Tools

Each `[tools.<name>]` table selects the toolset provider `<name>` and is passed to it
unchanged.

```toml
[tools.sql]                 # provider "sql" (mcp-tools-sql)
query_config = "C:/Users/me/.mcp-tools-sql/queries.toml"
# database_config = "..."   # optional; package default

[tools.workspace]           # provider "workspace" (mcp-workspace)
project_dir = "C:/Users/me/work/reports"
```

- No `[tools]` table → no tools.
- Keys and path rules belong to the provider. Both current providers require absolute
  paths (`~` allowed) and warn on unknown keys. `verify` shows the provider's checks.
- Another toolset package: install it and add its table. Writing one: see the
  [mcp-coder-utils README](https://github.com/MarcusJellinghaus/mcp-coder-utils)
  (toolset provider contract).
- Keep the mcp-tools-sql query config outside the workspace – the model can write files
  there.

## `agent-workbench verify`

Checks the setup and sends a live test prompt.

```bat
agent-workbench verify
agent-workbench verify --check-models
agent-workbench --log-level DEBUG verify
```

Sections: CONFIG, LLM PROVIDER, EFFECTIVE CONFIG, LLM PROVIDER DETAILS (ending with the
test prompt), TOOLS (the toolset providers' own checks) and, when provider packages are
missing, INSTALL INSTRUCTIONS.

- `--check-models` also lists the backend's available models. Advisory: it does not
  affect the exit code.
- TOOLS checks may connect (e.g. to the database); the UI start runs them without
  connecting.
- Exit code 0 when the config, the provider checks, the test prompt and the TOOLS checks
  all pass; else 1.
- `--log-level DEBUG` shows connection diagnostics when the test prompt fails.

## `agent-workbench prompt "<text>"`

Sends one prompt and prints the answer.

```bat
agent-workbench prompt "Summarise LangChain in one sentence"
agent-workbench prompt --timeout 120 "..."
```

- `--timeout` – request timeout in seconds (default 60).
- On any error: prints a message and exits with code 1.

## `agent-workbench-ui`

Opens a local chat page with the configured LLM (LangGraph agent with the configured
tools).

```bat
agent-workbench-ui
agent-workbench-ui --log-level DEBUG
```

- Start: checks that `langgraph`, `langgraph.checkpoint.sqlite`, `langchain_core`, `greenlet`
  and `aiohttp` are installed (else: `pip install "agent-workbench[langchain]"`), then runs
  the full `verify` including the test prompt. On failure it prints the verify report and
  exits with code 1. Then it builds the configured toolsets once and closes them; a build
  error stops the start.
- Serves on `http://127.0.0.1:8000` only and opens the browser. `CHAINLIT_PORT` changes the
  port; `CHAINLIT_HOST` is always forced to `127.0.0.1`.
- Chainlit's files (`.chainlit/config.toml`, rewritten on every start, and `.files/`) live in
  `%USERPROFILE%\.agent_workbench\chainlit`. No `.env` file is read. Chainlit env vars for
  features the app does not configure (database, Literal AI, Slack / Discord / Teams, custom
  auth, auth cookie, root path, SSL) are ignored with a warning.
- Limits per turn: 50 agent steps, 300 s without a stream event (paused while tools run),
  3600 s overall. Token usage is shown after each answer; the Stop button cancels the turn.
- Tool calls appear as steps with their arguments and a truncated result.
- `--log-level` – level of the app log, default `INFO`. App log:
  `%USERPROFILE%\.agent_workbench\logs\agent_workbench_ui_<timestamp>.log`, one per run;
  the console shows `OUTPUT` and above.
- Tool-call log: `%USERPROFILE%\.agent_workbench\logs\tool_calls.jsonl`, one line per call
  (user, tool, parameters, outcome, result size, duration; no results).

### Sessions

- Conversations are listed in the sidebar and can be resumed and deleted. They are kept
  until you delete them.
- Stored in `%USERPROFILE%\.agent_workbench\sessions\`: `checkpoints.sqlite` (agent state)
  and `chainlit.sqlite` (what the page shows), each with SQLite's `-wal` / `-shm` side
  files. Delete these files only while the app is stopped.
- Sign-in is automatic as the OS user (the login page may flash briefly).
- The sidebar lists at most 1000 conversations; older ones are not listed and cannot be
  deleted in the UI.
- After a resume, the session token total restarts at 0.
- The thumbs up / down buttons are visible, but feedback is not supported.

## Quality checks

| Check | Command |
|---|---|
| Tests | `pytest` |
| Types | `tools\mypy.bat` |
| Lint | `tools\ruff_check.bat`, `tools\pylint_check_for_errors.bat` |
| Format | `ruff format src tests tools` |
| Layering | `tools\lint_imports.bat`, `tools\tach_check.bat` |
| Dead code | `tools\vulture_check.bat` |
| Dependencies | `tools\deptry_check.bat` |

CI runs all of them (`.github/workflows/ci.yml`).

## Working with Claude Code

This repo uses [mcp-coder](https://github.com/MarcusJellinghaus/mcp_coder) workflows.
Start Claude Code with `claude.bat` (sets up the MCP servers from `.mcp.json`).
Project instructions: [.claude/CLAUDE.md](.claude/CLAUDE.md).
