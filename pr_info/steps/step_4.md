# Step 4 – Delete: checkpointer first, deleted set, WAL checkpoints

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (sections "Delete", "Database files"), then
implement this step (`pr_info/steps/step_4.md`) with TDD. One commit.

## WHERE
- `src/agent_workbench/apps/ui_data_layer.py`
- `tests/apps/conftest.py` (`data_layer` fixture gets a checkpointer)
- `tests/apps/test_ui_data_layer_delete.py` (new)

## WHAT
```python
CheckpointerProvider = Callable[[], Awaitable[Any]]

class SessionDataLayer(...):
    def __init__(self, db_path: Path, checkpointer: CheckpointerProvider) -> None: ...
    async def delete_thread(self, thread_id: str) -> None: ...
    async def finish_turn(self, thread_id: str) -> None: ...   # the one public method on_message uses
    async def _delete_everywhere(self, thread_id: str) -> None: ...
    async def _checkpoint_wal(self) -> None: ...
    # update_thread / create_step: return early for ids in self._deleted
```

## HOW
- `self._checkpointer = checkpointer`; `self._deleted: set[str] = set()`.
- `from agent_workbench.apps.agent import checkpoint_wal` for the saver's WAL checkpoint.
- `_checkpoint_wal`: own engine connection, not `execute_sql`:
  `async with self.engine.connect() as conn: row = (await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")).first()`;
  busy (`row[0]`) → warning; any exception → logged, never raised.
- `update_thread`: `if thread_id in self._deleted: return` before anything else.
- `create_step`: `if step_dict.get("threadId") in self._deleted: return` before the copy
  (covers `update_step`, which goes through `create_step`).

## ALGORITHM
```
delete_thread(id):
    self._deleted.add(id)
    try: await self._delete_everywhere(id)
    except BaseException: self._deleted.discard(id); raise   # thread stays listed, retryable

_delete_everywhere(id):
    saver = await self._checkpointer(); await saver.adelete_thread(id)   # failure propagates
    await super().delete_thread(id)                                      # feedback, elements, steps, thread
    await checkpoint_wal(saver); await self._checkpoint_wal()            # after adelete_thread returned

finish_turn(id):
    if id in self._deleted: await self._delete_everywhere(id)
```

## DATA
- `_deleted`: in-process `set[str]`, lives on the instance, never persisted.

## Tests (write first), `tests/apps/test_ui_data_layer_delete.py`
Fixture: `data_layer` from conftest now builds a real saver via
`agent.open_checkpointer(tmp_path / "checkpoints.sqlite")` and passes
`AsyncMock(return_value=saver)`-style provider; closes the saver's connection at teardown.
- Delete removes the conversation from both databases (acceptance): thread + step + feedback
  on that step in `chainlit.sqlite`, a checkpoint in `checkpoints.sqlite` (`saver.aput` or a
  graph turn with the scripted model); after `delete_thread`, no rows in `threads`, `steps`,
  `feedbacks` and `saver.aget_tuple(...)` is `None`.
- Delete on a fresh checkpointer database works (no turn ever ran).
- Failing checkpointer delete (provider returns a saver whose `adelete_thread` raises):
  exception propagates, thread still listed by `get_all_user_threads`, id not in `_deleted`.
- After a delete, `update_thread` and `create_step` for that id write nothing (raw row count 0).
- `finish_turn` on a deleted id removes checkpoints written after the delete; on a
  non-deleted id it does nothing (thread still present).
- `_checkpoint_wal` logs and does not raise when the engine connection fails.
