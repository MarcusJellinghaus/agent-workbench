# Step 1 – Persistent checkpointer in `apps/agent.py`

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (sections "Database files", "Agent state:
checkpointer", "Dependencies"), then implement this step (`pr_info/steps/step_1.md`) with
TDD: tests first, then code, then all checks. One commit.

## Preconditions
- `langgraph.checkpoint.sqlite.aio` and `aiosqlite` must be importable in the MCP check
  environment (`search_library_files` / `get_library_source`). If not: write one line to
  `pr_info/.blocked.txt` and stop.
- Read the installed `langgraph-checkpoint-sqlite` version (scratch probe,
  `importlib.metadata.version`). If newer than 3.1.3, re-check with `get_library_source`:
  `AsyncSqliteSaver.__init__` captures the running loop, exposes `conn` and `lock`, its
  writes run execute + commit under `lock`, and `setup()` sets WAL. If any of that no
  longer holds: write one line to `pr_info/.blocked.txt` and stop.

## WHERE
- `src/agent_workbench/apps/agent.py`
- `src/agent_workbench/apps/ui_launcher.py` (`_UI_DEPENDENCIES`)
- `pyproject.toml` (`[langchain-base]`)
- `tests/apps/test_agent_checkpointer.py` (new), `tests/apps/test_agent_graph.py`,
  `tests/apps/test_ui_launcher.py`

## WHAT
```python
logger = logging.getLogger(__name__)
_runtime_lock = asyncio.Lock()

def sessions_dir() -> Path: ...                      # <app-data>/sessions, created
async def open_checkpointer(path: Path) -> AsyncSqliteSaver: ...
async def checkpoint_wal(saver: AsyncSqliteSaver) -> None: ...
async def get_runtime() -> Runtime: ...              # now locked, SQLite saver
async def close_runtime() -> None: ...               # closes saver.conn, resets _runtime

@dataclass(frozen=True)
class Runtime:
    graph: Any
    chat_model: Any
    llm_config: LLMConfig
    checkpointer: Any
```

## HOW
- `from agent_workbench.adapters import config` and call `config.app_data_dir()` (not a
  `from … import app_data_dir` copy), so tests patch `adapters.config.app_data_dir`.
  `mkdir(parents=True, exist_ok=True)`.
- `import aiosqlite`; `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver`;
  drop the `InMemorySaver` import. Covered by the existing `langgraph` contract; add an
  `aiosqlite` `forbidden` contract in `.importlinter` (allowed in `agent_workbench.apps.**`),
  same shape as `langgraph_isolation`.
- `get_runtime` docstring / comments: remove the "#16 swaps the saver" notes.
- `pyproject.toml`: `"langgraph-checkpoint-sqlite>=<installed, at least 3.1.2>"` next to
  `langgraph` in `[langchain-base]`, comment naming the three GHSA ids from the issue;
  `"aiosqlite>=<installed>"` in core `dependencies` next to `chainlit` (imported directly
  from this step on, so deptry needs it declared).
- `_UI_DEPENDENCIES = ("langgraph", "langgraph.checkpoint.sqlite", "langchain_core")`.

## ALGORITHM
```
open_checkpointer(path):
    conn = await aiosqlite.connect(path)
    try: execute "PRAGMA secure_delete=ON"; saver = AsyncSqliteSaver(conn); await saver.setup()
    except BaseException: await conn.close(); raise
    return saver

checkpoint_wal(saver):           # after adelete_thread has returned, never around it
    try: async with saver.lock: row = fetchone("PRAGMA wal_checkpoint(TRUNCATE)")
         if row[0]: logger.warning("busy ...")
    except Exception: logger.exception(...)   # never raises

get_runtime():
    async with _runtime_lock:
        if _runtime is None:
            llm_config, chat_model built first
            saver = await open_checkpointer(sessions_dir() / "checkpoints.sqlite")
            try: graph = build_graph(chat_model, [], saver)
            except BaseException: await saver.conn.close(); raise
            _runtime = Runtime(graph, chat_model, llm_config, saver)
    return _runtime
```

## DATA
- `sessions_dir()` → `Path`; `open_checkpointer` → set-up `AsyncSqliteSaver`;
  `checkpoint_wal`, `close_runtime` → `None`.

## Tests (write first)
`tests/apps/test_agent_checkpointer.py`:
- Simulated restart (acceptance): saver 1 + graph on `tmp_path/"c.sqlite"`, turn 1 with
  `make_scripted_chat_model`; close; saver 2 + new graph on the same file, same `thread_id`:
  state contains turn 1, and the second turn's model input (record it in the script
  callback or a capturing `_agenerate`) includes turn 1's messages.
- `secure_delete` is 1 on `saver.conn` (`PRAGMA secure_delete`).
- `adelete_thread` on a fresh database does not raise; after a turn, delete + `checkpoint_wal`
  leaves no checkpoints for the thread (`aget_tuple` is `None`).
- `checkpoint_wal` logs (does not raise) when the execute fails (patch `saver.conn.execute`).
- `get_runtime`: concurrent first calls (`asyncio.gather`) build once; patch
  `agent._runtime_lock` with a fresh `asyncio.Lock()` and `agent._runtime` with `None`;
  `config.app_data_dir` patched to `tmp_path`; `close_runtime()` at the end.
- Failure after the connection is opened (patch `build_graph` to raise) closes the connection.
- `sessions_dir()` is `<patched app-data>/sessions` and exists.

`tests/apps/test_agent_graph.py`: `test_get_runtime_builds_once` patches
`config.app_data_dir` to `tmp_path`, asserts `first.checkpointer` is set, ends with
`await agent.close_runtime()`.

`tests/apps/test_ui_launcher.py`: adjust any test listing `_UI_DEPENDENCIES`; a missing
`langgraph.checkpoint.sqlite` is reported by name.

Every test closes its connections (Windows temp-dir cleanup).
