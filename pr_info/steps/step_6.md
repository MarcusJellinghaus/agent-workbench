# Step 6 – Handlers: data layer, header auth, resume, shutdown, end-of-turn re-delete

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (sections "Local user and auth secret",
"Resume", "Delete" – deleting while answering, "Imports, contracts and tooling"), then
implement this step (`pr_info/steps/step_6.md`) with TDD. One commit.

## WHERE
- `src/agent_workbench/apps/ui_handlers.py`
- `tests/apps/test_ui_handlers.py`
- `vulture_whitelist.py`

## WHAT
```python
logger = logging.getLogger(__name__)

@cl.data_layer
def data_layer() -> SessionDataLayer: ...

@cl.header_auth_callback
async def header_auth(headers: Any) -> cl.User: ...

@cl.on_chat_resume
async def on_chat_resume(thread: dict[str, Any]) -> None: ...

@cl.on_app_shutdown
async def on_app_shutdown() -> None: ...

async def _checkpointer() -> Any: ...          # (await get_runtime()).checkpointer
async def _finish_turn(thread_id: str) -> None: ...
```
Decorators carry `# type: ignore[untyped-decorator]` as `on_message` does.

## HOW
- Imports: `getpass`, `logging`, `from chainlit.data import get_data_layer`,
  `from agent_workbench.apps.agent import close_runtime, get_runtime, run_turn, sessions_dir`,
  `from agent_workbench.apps.ui_data_layer import SessionDataLayer`.
- Module docstring: Chainlit is imported here, in `ui_data_layer` (imported only by this
  module) and in `ui_launcher._run_chainlit`.
- `data_layer()` (sync): `SessionDataLayer(sessions_dir() / "chainlit.sqlite", _checkpointer)`
  – path read at call time.
- `header_auth`: `cl.User(identifier=getpass.getuser())`.
- `on_chat_resume`: `runtime = await get_runtime()`;
  `await runtime.checkpointer.aget_tuple({"configurable": {"thread_id": thread["id"]}})`;
  `None` → `logger.warning` (user can still continue).
- `on_app_shutdown`: `await close_runtime()`.
- `_finish_turn`: `layer = get_data_layer()`; `if isinstance(layer, SessionDataLayer): await layer.finish_turn(thread_id)` – not via `cl.*` (the `fake_cl` fixture replaces `cl`).
  Any `Exception` from `finish_turn` (e.g. an `adelete_thread` failure) is caught and
  logged (`logger.exception`), never raised: it runs in `on_message`'s `finally` and must
  not replace a `CancelledError` from Stop or the turn's own error.
- `on_message`: read `thread_id = cl.context.session.thread_id` once; wrap the turn and the
  sends in `try: ... finally: await _finish_turn(thread_id)`. `CancelledError` still propagates.

## ALGORITHM
```
on_message(message):
    if message is None: return
    thread_id = cl.context.session.thread_id
    try: existing body (run_turn(..., thread_id, ...), sends)
    finally: await _finish_turn(thread_id)
```

## DATA
- `header_auth` → `cl.User`; the others → `None`.

## Tests (write first), `tests/apps/test_ui_handlers.py`
- `header_auth` returns a user whose identifier is `getpass.getuser()` (acceptance).
- `data_layer()` with `adapters.config.app_data_dir` patched to `tmp_path` builds a
  `SessionDataLayer` on `tmp_path/"sessions"/"chainlit.sqlite"`; `await layer.close()`.
- `on_chat_resume`: runtime mock whose `checkpointer.aget_tuple` returns `None` → warning
  logged; returns a tuple → no warning.
- `on_app_shutdown` awaits `close_runtime` (patched).
- `on_message` with `chainlit.data._data_layer` set to `MagicMock(spec=SessionDataLayer)`
  (with `finish_turn = AsyncMock()`): `finish_turn(THREAD_ID)` awaited after a normal turn,
  after an error turn and after Stop (`CancelledError` still raised).
- `finish_turn` raising (`AsyncMock(side_effect=RuntimeError)`) after Stop: the handler still
  re-raises `CancelledError` and the failure is logged.
- End-to-end (acceptance): real `SessionDataLayer` + real saver on `tmp_path`, scripted
  model graph; delete the thread, then a turn on it ends (normally and by Stop) → no
  checkpoints for it (`aget_tuple` is `None`).
- Existing tests keep passing with the autouse fixture (`_data_layer` is `None` → no call).

## Tooling
- `vulture_whitelist.py`: `data_layer`, `header_auth`, `on_chat_resume`, `on_app_shutdown`
  and data-layer overrides, as far as vulture reports them.
- Run lint-imports (the Chainlit contract already allows `apps.**`), and tach only if
  `run_tach_check` fails.
