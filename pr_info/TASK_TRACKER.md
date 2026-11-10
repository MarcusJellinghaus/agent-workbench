# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: Persistent checkpointer in `apps/agent.py` — [step_1.md](./steps/step_1.md)
- [x] Implementation: tests in `test_agent_checkpointer.py`, `test_agent_graph.py`, `test_ui_launcher.py`; `sessions_dir`, `open_checkpointer`, `checkpoint_wal`, locked `get_runtime`, `close_runtime`, `Runtime.checkpointer`; `_UI_DEPENDENCIES`, `pyproject.toml` floors / DEP002, `.importlinter` aiosqlite contract
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: SQLite schema for Chainlit's data layer — [step_2.md](./steps/step_2.md)
- [x] Implementation: tests in `test_ui_data_layer_schema.py` (coverage, idempotence, WAL, missing column); `_DDL`, `expected_columns`, `prepare_database`, `_columns` in new `ui_data_layer.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `SessionDataLayer` — engine, `secure_delete`, tags and JSON fixes — [step_3.md](./steps/step_3.md)
- [x] Implementation: conftest fixtures and tests in `test_ui_data_layer.py`; `SessionDataLayer` (`__init__`, `update_thread`, `create_step`, `get_all_user_threads`), `_encode_tags`, `_decode_json`, `_set_secure_delete`; `pyproject.toml` floors / DEP002, `.importlinter` sqlalchemy contract, `_UI_DEPENDENCIES`, `vulture_whitelist.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: Delete — checkpointer first, deleted set, WAL checkpoints — [step_4.md](./steps/step_4.md)
- [x] Implementation: tests in `test_ui_data_layer_delete.py`, `data_layer` fixture with real saver; `CheckpointerProvider`, `delete_thread`, `finish_turn`, `_delete_everywhere`, `_checkpoint_wal`, early returns for deleted ids
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Launcher — auth secret, removed cookie env vars, `allow_thread_sharing` — [step_5.md](./steps/step_5.md)
- [x] Implementation: tests in `test_ui_env.py`; `AUTH_SECRET_FILE`, `_auth_secret`, `CHAINLIT_AUTH_SECRET` in `prepare_chainlit_env`, `_REMOVED_ENV_VARS`, `allow_thread_sharing = false` in `_CONFIG_TEMPLATE`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 6: Handlers — data layer, header auth, resume, shutdown, end-of-turn re-delete — [step_6.md](./steps/step_6.md)
- [x] Implementation: tests in `test_ui_handlers.py` (incl. end-to-end delete during a turn); `data_layer`, `header_auth`, `on_chat_resume`, `on_app_shutdown`, `_checkpointer`, `_finish_turn`, `on_message` `try/finally`; `vulture_whitelist.py`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 7: Docs — README, security design, architecture — [step_7.md](./steps/step_7.md)
- [x] Implementation: `README.md`, `docs/security/security_design.md`, `docs/architecture/architecture.md`; `check_file_size` passes
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

## Pull Request
- [ ] PR review: review the full branch diff against `main` and address findings
- [ ] PR summary prepared (incl. manual smoke test: restart, resume, delete; page and model agree after resume)
