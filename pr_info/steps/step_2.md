# Step 2 – SQLite schema for Chainlit's data layer

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (section "Chainlit data layer": tables,
coverage test, existing databases), then implement this step (`pr_info/steps/step_2.md`)
with TDD. One commit.

## Preconditions
- Read the installed Chainlit version. If newer than 2.12.0, re-check with
  `get_library_source` / `search_library_files` that the `INSERT`s in
  `chainlit/data/sql_alchemy.py` use `ON CONFLICT ("id")` and that `get_all_user_threads`
  joins `feedbacks`. If not: write one line to `pr_info/.blocked.txt` and stop.

## WHERE
- `src/agent_workbench/apps/ui_data_layer.py` (new; stdlib only in this step)
- `tests/apps/test_ui_data_layer_schema.py` (new)

## WHAT
```python
"""Chainlit data layer on SQLite: schema and (step 3) the SessionDataLayer subclass."""
logger = logging.getLogger(__name__)
_DDL: str                                            # CREATE TABLE IF NOT EXISTS × 5
def expected_columns() -> dict[str, list[str]]: ...  # from _DDL via :memory:
def prepare_database(path: Path) -> None: ...        # tables, WAL, missing-column check
def _columns(conn: sqlite3.Connection) -> dict[str, list[str]]: ...
```

## HOW
- `_DDL`: adapted from the Chainlit SQLAlchemy docs to SQLite. Tables `users`, `threads`,
  `steps`, `elements`, `feedbacks`. Quoted camelCase column names; `TEXT` instead of
  `UUID` / `JSONB` / `TEXT[]`; `"id"` primary key in every table; plus the 2.12.0 columns
  the docs lack (steps `"autoCollapse"`, `"icon"`; elements `"path"`, `"autoPlay"`,
  `"playerConfig"`); `feedbacks."threadId"` nullable. No reliance on `ON DELETE CASCADE`.
  The coverage test is the final judge of the column list.
- Every connection uses `contextlib.closing(sqlite3.connect(...))` (not `with sqlite3.connect`).
- Tables in a module-level `_TABLES` tuple, used by `_columns`.

## ALGORITHM
```
expected_columns():
    with closing(sqlite3.connect(":memory:")) as mem: mem.executescript(_DDL); return _columns(mem)

prepare_database(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(_DDL); conn.execute("PRAGMA journal_mode=WAL")
        have = _columns(conn)
        for table, cols in expected_columns().items():
            for col in cols not in have[table]: logger.error("chainlit.sqlite: %s.%s missing ...", table, col)
```

## DATA
- `expected_columns()` / `_columns()` → `{table: [column, ...]}` (from `PRAGMA table_info`).

## Tests (write first)
- Coverage (acceptance): every key of `chainlit.types.ThreadDict` minus `steps`,
  `elements` ⊆ `threads` columns; `chainlit.step.StepDict` minus `feedback` ⊆ `steps`;
  `chainlit.element.ElementDict` ⊆ `elements`; `dataclasses.fields(chainlit.types.Feedback)`
  ⊆ `feedbacks`. Use `__annotations__` / `get_type_hints` keys of the TypedDicts.
- `prepare_database(tmp_path / "c.sqlite")` creates all five tables; is idempotent
  (second call fine, no error logged); `PRAGMA journal_mode` reads `wal`.
- A database whose `steps` table lacks `"icon"` (create it by hand first) logs an error
  naming `steps.icon`; nothing raised.
