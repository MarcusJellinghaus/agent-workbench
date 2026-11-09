# Summary – #15 Chainlit chat page with a LangGraph agent (no tools yet)

Step 3 of epic #12. The user runs `agent-workbench-ui`; after the dependency check and the
full `verify`, a local Chainlit page opens on `127.0.0.1` and they chat with the configured
LLM through a hand-built LangGraph graph (no tools yet), with streaming, limits and token
usage. The issue text (#15) is the specification; these files plan how to build it.

mcp_coder source for every copy and pattern: `origin/main` at **`033a9d05`** (fetch first;
read with `mcp__mcp-workspace__git`, `command="show"`, `args=["033a9d05:<path>"]`,
`reference_name="mcp_coder"`, `compact=False`). Each copied file's header names the source
path and this commit.

## Architectural / design changes

### New in `agent_workbench.apps` (first code in the layer)

| Module | Responsibility | Imports Chainlit? |
|---|---|---|
| `apps/agent.py` | `build_graph` (model node → `ToolNode`, `tools_condition`), `get_runtime` (process-wide async lazy getter: chat model, `InMemorySaver`, graph), `run_turn` (one turn, Chainlit-free) | no |
| `apps/origin_check.py` | Plain ASGI middleware rejecting foreign `Origin` headers (HTTP + WebSocket); `local_origins(port)` | no |
| `apps/ui_launcher.py` | `main()` of `agent-workbench-ui`; dependency check; `verify`; Chainlit environment cleanup; `config.toml` writer; `_run_chainlit` wrapper (only place importing `chainlit.cli`) | only inside `_run_chainlit` |
| `apps/ui_handlers.py` | Chainlit `on_message` handler; adds the origin middleware to `chainlit.server.app` on import | yes (top level) |
| `apps/ui_target.py` | Shim passed to `run_chainlit`: one absolute import of `ui_handlers` | indirectly |

No `apps` module is named like a top-level package (Chainlit puts the shim's folder on
`sys.path` while loading it).

### Key design decisions (KISS)

- **Turn function with a callback, not a generator.**
  `run_turn(graph, chat_model, llm_config, text, thread_id, on_text, token_usage, *, idle_timeout, overall_timeout) -> str | None`
  streams text through `on_text`, updates `token_usage` only for a completed turn and
  returns an error message or `None`. Timeouts and error handling live in one place; tests
  pass `list.append`-style callbacks and their own graph / model / config.
- **Timeouts:** overall cap via `asyncio.timeout(overall)`; inactivity via a nested
  `asyncio.timeout(idle)` rescheduled after every stream event; `expired()` on each tells
  which fired (also when langgraph surfaces the cancel as `NodeCancelledError`).
- **Errors, in order:** timeout → own message; `GraphRecursionError` → own message;
  `NodeCancelledError` → timeout message if a timer expired, else re-raised as
  `asyncio.CancelledError`; any other `Exception` →
  `asyncio.to_thread(map_provider_error, …)`, the mapped exception's text is the message.
  `CancelledError` (Stop) is never caught.
- **Final text fallback:** if no `on_chat_model_stream` delta arrived in the turn, the last
  `AIMessage` text from `graph.aget_state(...)` is passed to `on_text`.
- **Runtime getter without a lock:** building model, saver and graph contains no `await`, so
  a module-level cache in an `async def get_runtime()` is race-free. #16 adds a lock with the
  first `await` (async SQLite saver).
- **One public usage function:** `adapters.llm.add_usage(total, msg)` wraps the copied
  `_extract_usage` / `_sum_usage`.
- **OpenAI streamed usage:** `adapters.llm.create_chat_model` mirrors langchain_openai's own
  `stream_usage` default by building the same class with the same settings minus the custom
  HTTP clients (no network call), and copies the value onto the built model.
- **One Chainlit handler:** `on_message` gets or creates the `TokenUsage` in
  `cl.user_session` (per chat; "New chat" starts a new session). Usage is appended under the
  answer when `TokenUsage.has_data`.
- **Chainlit isolation:** before the first `import chainlit` the launcher sets
  `CHAINLIT_APP_ROOT` to `<app-data>/chainlit`, `CHAINLIT_ENV_FILE` to a never-created file
  there, removes the listed env vars (warning per var that was set), forces
  `CHAINLIT_HOST=127.0.0.1`, and rewrites `.chainlit/config.toml` from a fixed template on
  every start. The test conftest calls the same function, so the env-var list exists once.
- **Origin check:** Chainlit's Socket.IO server disables its origin check; the middleware
  closes that gap for HTTP and WebSocket.

### Dependencies and contracts

- `chainlit>=2.12.0` → core dependencies, and `langgraph>=1.2.9` (mcp_coder's floor) →
  `[langchain-base]`: both declared before step 4 so the environment has them, with a
  temporary deptry `DEP002` ignore that step 4 (langgraph) and step 8 (chainlit) remove.
- No `langchain-mcp-adapters`.
- import-linter: `chainlit_isolation` and `langgraph_isolation` (`apps.**` only);
  `langchain_core_isolation` also allows `agent_workbench.apps.**`.
- mypy: mcp_coder's `langgraph`, `langgraph.*` override verbatim; Chainlit type-checked
  unless its types fail (then an override, named in the PR).
- `[project.scripts] agent-workbench-ui = "agent_workbench.apps.ui_launcher:main"`.

## Files created / modified

### Created
```
src/agent_workbench/core/types.py               # copy: TokenUsage, format_token_count
src/agent_workbench/apps/agent.py
src/agent_workbench/apps/origin_check.py
src/agent_workbench/apps/ui_launcher.py
src/agent_workbench/apps/ui_handlers.py
src/agent_workbench/apps/ui_target.py
tests/langchain_doubles.py                      # copy: make_scripted_chat_model
tests/core/test_types.py                        # copy of mcp_coder's TokenUsage tests
tests/adapters/test_llm_stream_usage.py
tests/apps/__init__.py
tests/apps/conftest.py
tests/apps/test_agent_graph.py
tests/apps/test_agent_turn.py
tests/apps/test_origin_check.py
tests/apps/test_ui_env.py
tests/apps/test_ui_launcher.py
tests/apps/test_ui_handlers.py
```

### Modified
```
src/agent_workbench/adapters/llm.py             # add_usage, OpenAI stream_usage mirror
src/agent_workbench/adapters/config.py          # app_data_dir()
tests/adapters/test_llm.py                      # add_usage tests
tests/adapters/test_config.py                   # app_data_dir test
pyproject.toml                                  # chainlit, langgraph, script, mypy overrides
.importlinter                                   # chainlit / langgraph contracts, langchain_core allows apps
vulture_whitelist.py                            # (#15) entries cleaned, fake model overrides
README.md
docs/architecture/architecture.md
docs/security/security_design.md
```

`tach.toml` changes only if `run_tach_check` fails.

## Steps

1. `core.types`: copy `TokenUsage` / `format_token_count` and their tests.
2. `adapters.llm.add_usage`; vulture `(#15)` usage entries.
3. OpenAI streamed usage in `adapters.llm.create_chat_model`.
4. Agent graph and runtime getter (`langgraph` dependency, contracts, fake model copy).
5. Turn function `run_turn` (streaming, limits, errors, Stop, usage).
6. Origin-check ASGI middleware.
7. Chainlit environment and `config.toml` (`app_data_dir`, test conftest).
8. Launcher `main` and `agent-workbench-ui` script (`chainlit` dependency).
9. Chainlit handler module and shim.
10. Docs (README, architecture, security design).

## Rules for every step

- Tests first, then the code; exactly one commit per step.
- Pytest: `extra_args=["-n", "auto", "-m", "not integration"]`.
- Before the commit: `run_format_code`, then pylint, pytest, mypy, ruff, lint-imports,
  vulture, deptry must pass (tach if layers changed).
- Scratch probes go to `.scratch/` and are deleted before the commit
  (`delete_directory(".scratch", recursive=True)`). Probes that import Chainlit set
  `CHAINLIT_APP_ROOT` to an existing temp folder and `CHAINLIT_ENV_FILE` to an absolute
  non-existent path before the first `import chainlit`.
- Package precondition: if a step needs `chainlit`, `langgraph`, `langchain_core` or
  `langchain_openai` and `mcp__mcp-tools-py__search_library_files(scope=<module>, glob="__init__.py")`
  cannot resolve it, write one line to `pr_info/.blocked.txt` and stop.
