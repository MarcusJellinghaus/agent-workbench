# Step 9 – Chainlit handler module and shim

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 9: `apps/ui_handlers.py`
(origin middleware on `chainlit.server.app`, the `on_message` handler) and the shim
`apps/ui_target.py`. Tests first, then code; all checks pass; one commit.

## Precondition
`chainlit` and `langgraph` resolvable; otherwise write one line to `pr_info/.blocked.txt`
and stop.

## WHERE
- Create `src/agent_workbench/apps/ui_handlers.py`
- Create `src/agent_workbench/apps/ui_target.py`
- Create `tests/apps/test_ui_handlers.py`
- Modify `vulture_whitelist.py` only for names vulture reports
- Modify `pyproject.toml` only if Chainlit's types fail mypy here (first `src` use of
  `cl.Message`, `cl.on_message`, `chainlit.server.app`): add the `chainlit`
  `ignore_missing_imports` / `follow_imports = "skip"` override and name it in the PR

## WHAT
```python
# ui_handlers.py
import chainlit as cl
from chainlit.server import app

app.add_middleware(OriginCheckMiddleware, allowed_origins=local_origins(chainlit_port()))

@cl.on_message
async def on_message(message: cl.Message | None) -> None: ...
```
```python
# ui_target.py – loaded by run_chainlit by file path, without a parent package
"""Chainlit target: imports the handler module (absolute imports only)."""
import agent_workbench.apps.ui_handlers  # noqa: F401
```

## HOW
- Only this module (and `_run_chainlit`) imports Chainlit.
- Middleware is added at import: `run_chainlit` loads the target before serving, and
  middleware cannot be added after start.
- `on_message` uses the process-wide `agent.get_runtime()`; `thread_id` =
  `cl.context.session.thread_id`.
- `TokenUsage` lives in `cl.user_session` under `"token_usage"`, created on first use
  (one per chat; "New chat" starts a new session). No `on_chat_start`.
- A missing message is ignored (edit is off in the config, but the handler must not fail).
- Stop: Chainlit cancels the task and posts "Task manually stopped."; the handler adds
  nothing and catches nothing.

## ALGORITHM
```
if message is None: return
runtime = await get_runtime()
usage = cl.user_session.get("token_usage") or TokenUsage(); cl.user_session.set("token_usage", usage)
answer = cl.Message(content="")
error = await run_turn(runtime.graph, runtime.chat_model, runtime.llm_config, message.content,
                       cl.context.session.thread_id, answer.stream_token, usage)
if error: (send answer if it has content); await cl.Message(content=error).send(); return
if usage.has_data: await answer.stream_token(f"\n\n{usage.display_text()}")
await answer.send()
```

## DATA
No return values; messages in the Chainlit page.

## Tests (`tests/apps/test_ui_handlers.py`)
Importing the module is safe thanks to the conftest (temp app root; never runs the server
lifespan).
- After import, `chainlit.server.app.user_middleware` contains `OriginCheckMiddleware` with
  the local origins.
- `on_message` with `ui_handlers.cl` patched (`MagicMock`; `Message` returns objects with
  `AsyncMock` `stream_token` / `send`; `user_session` backed by a dict), `get_runtime` and
  `run_turn` patched:
  - success → `run_turn` gets the thread id and the session's `TokenUsage`; usage line
    streamed when `has_data`; answer sent;
  - error → error message sent;
  - `None` message → `run_turn` not called;
  - two calls in the same session reuse one `TokenUsage`;
  - Stop: `run_turn` patched to raise `asyncio.CancelledError` → `on_message` raises
    `CancelledError` (`pytest.raises`), no `Message(...).send()` and no `stream_token` call.
- Importing `ui_target` imports `ui_handlers` (module in `sys.modules`).

## Checks / commit
pylint, pytest, mypy, ruff, lint-imports, vulture, deptry, tach. Commit:
`feat(apps): Chainlit chat handler and target shim`.

## Manual smoke test (user, after this step)
`agent-workbench-ui` → page opens on `127.0.0.1:8000`; chat; see token-by-token streaming
and the usage line; press Stop during an answer. Result goes into the PR description.
