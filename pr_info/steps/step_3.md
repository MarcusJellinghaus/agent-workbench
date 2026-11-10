# Step 3 – `SessionDataLayer`: engine, `secure_delete`, tags and JSON fixes

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (sections "Chainlit data layer",
"Dependencies", "Imports, contracts and tooling", "Tests"), then implement this step
(`pr_info/steps/step_3.md`) with TDD. One commit.

## Preconditions
- `sqlalchemy` (with `sqlalchemy.ext.asyncio`), `aiosqlite`, `greenlet` and `aiohttp` must be
  importable in the MCP check environment. If not: write one line to
  `pr_info/.blocked.txt` and stop.
- Read installed versions (scratch probe, `importlib.metadata.version`) for `sqlalchemy`,
  `aiosqlite`, `aiohttp`. If SQLAlchemy is newer than 2.1.6 or Chainlit newer than 2.12.0,
  re-check: `SQLAlchemyDataLayer.__init__` passes `conninfo` only to `create_async_engine`
  and stores `self.engine`; `execute_sql` swallows exceptions; `create_step` calls
  `update_thread`; `update_step` calls `create_step`. If not: write one line to
  `pr_info/.blocked.txt` and stop.

## WHERE
- `src/agent_workbench/apps/ui_data_layer.py`
- `tests/apps/conftest.py`, `tests/apps/test_ui_data_layer.py` (new)
- `pyproject.toml`, `.importlinter`, `src/agent_workbench/apps/ui_launcher.py`
  (`_UI_DEPENDENCIES`), `tests/apps/test_ui_launcher.py`, `vulture_whitelist.py`

## WHAT
```python
class SessionDataLayer(SQLAlchemyDataLayer):  # type: ignore[misc]  # chainlit skipped by mypy
    def __init__(self, db_path: Path) -> None: ...
    async def update_thread(self, thread_id: str, name=None, user_id=None,
                            metadata=None, tags=None) -> None: ...
    async def create_step(self, step_dict: dict[str, Any]) -> None: ...
    async def get_all_user_threads(self, user_id=None, thread_id=None) -> list[dict] | None: ...

def _encode_tags(tags: Any) -> Any: ...      # list → json.dumps, else unchanged
def _decode_json(value: Any) -> Any: ...     # str → json.loads (incl. "null"), else unchanged
def _set_secure_delete(dbapi_conn: Any, _record: Any) -> None: ...
```
Step 4 adds the checkpointer provider and delete; keep the constructor easy to extend.

## HOW
- Module imports `sqlalchemy` (`URL`, `event`) and `from chainlit.data.sql_alchemy import
  SQLAlchemyDataLayer`. Module docstring: Chainlit is imported here and in `ui_handlers`
  only; only `ui_handlers` imports this module.
- URL: `URL.create("sqlite+aiosqlite", database=str(db_path))`, passed as `conninfo`
  (survives Windows paths and `%` / `#`).
- `__init__`: `prepare_database(db_path)` → `super().__init__(conninfo=url)` →
  `event.listen(self.engine.sync_engine, "connect", _set_secure_delete)`.
- `update_thread`: `super().update_thread(..., tags=_encode_tags(tags))` – `None` stays `None`.
- `create_step`: `step = dict(step_dict)`; if `"tags"` is a list, encode it in the copy;
  `await super().create_step(step)`. The caller's dict is untouched.
- `get_all_user_threads`: call super; for each thread decode `tags`, `metadata`; for each
  step decode `tags`, `metadata`, `generation`.
- `pyproject.toml`: `sqlalchemy[asyncio]` and `aiohttp` are already declared in core deps.
  Raise both floors to the installed versions (`aiohttp` at least 3.14.4,
  GHSA-2g87-pp6c-29x5). Drop `sqlalchemy` from `[tool.deptry.per_rule_ignores] DEP002`;
  `aiohttp` stays there (imported only by Chainlit's `sql_alchemy` module).
- `.importlinter`: `sqlalchemy` `forbidden` contract allowed in `agent_workbench.apps.**`
  (aiosqlite's contract came in step 1).
- `_UI_DEPENDENCIES` gains `"greenlet"`, `"aiohttp"` (after the existing entries).
- mypy: sqlalchemy and aiosqlite ship types; add an override only if mypy reports one.

## ALGORITHM
```
_decode_json(v): return json.loads(v) if isinstance(v, str) else v
for thread in threads or []:
    thread["tags"], thread["metadata"] = decode(...)
    for step in thread.get("steps") or []: decode tags, metadata, generation
return threads
```

## DATA
- `get_all_user_threads` → Chainlit's list of `ThreadDict` with decoded JSON values.

## Test fixtures (write first)
`tests/apps/conftest.py`, appended (keep the module-level `prepare_chainlit_env` first):
- autouse fixture `_chainlit_data_layer`: imports `chainlit.data` inside the fixture, saves
  `_data_layer` / `_data_layer_initialized`, sets `None` / `True`, yields, restores both.
- fixture `data_layer` (async): `SessionDataLayer(tmp_path / "chainlit.sqlite")`, sets
  `chainlit.data._data_layer` to it, yields, `await layer.close()`.
- Add both fixture names to `vulture_whitelist.py` if vulture reports them.

## Tests (write first), `tests/apps/test_ui_data_layer.py`
- Round trip (acceptance): `create_user`, `update_thread(thread_id, name, user_id, metadata)`,
  `create_step` inside `init_http_context()` (no user, in the running loop) with metadata and
  generation; `get_all_user_threads(user_id=...)` returns the thread with its steps, JSON
  columns decoded (dicts / lists, not strings).
- Thread with tags `["a"]` is saved and read back as `["a"]` (known tags bug).
- Thread without tags: after two `update_thread` calls, the raw `tags` column is `NULL`
  (read with stdlib `sqlite3` + `closing`), not `"null"`.
- Step with list tags: saved, read back decoded; the caller's dict still holds the list.
- Feedback without `threadId` (`upsert_feedback(Feedback(forId=..., value=1))`) is saved:
  row present in `feedbacks`.
- `secure_delete` is 1 on a data-layer engine connection
  (`async with layer.engine.connect()` → `exec_driver_sql("PRAGMA secure_delete")`).
- `_decode_json` accepts JSON strings, decoded values and `"null"`.
- `test_ui_launcher.py`: missing `greenlet` / `aiohttp` reported by name.
