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

### Step 1: Flat copies `llm_types`, `config_hints`, `ssl_setup`, `toml_utils` — [step_1.md](./steps/step_1.md)
- [x] Implementation: copy the four modules and their tests, update `pyproject.toml`, `.importlinter`, `vulture_whitelist.py`
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, vulture, deptry) — fix all issues
- [x] Commit message prepared

### Step 2: Copy the LangChain model layer (15 source modules) — [step_2.md](./steps/step_2.md)
- [x] Implementation: copy the modules, add packaging/extras, mypy, deptry, import-linter, vulture and large-file entries
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, vulture, deptry, tach, check_file_size) — fix all issues
- [x] Commit message prepared

### Step 3: Copy model-layer tests, part 1 (conftest, backends, http, exceptions, messages) — [step_3.md](./steps/step_3.md)
- [x] Implementation: trimmed conftest and the seven test copies, vulture whitelist if needed
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, vulture) — fix all issues
- [x] Commit message prepared

### Step 4: Copy model-layer tests, part 2 (contract, diagnostics, models, provider checks, resolve_target) — [step_4.md](./steps/step_4.md)
- [x] Implementation: the six test copies, vulture whitelist / large-files allowlist if needed
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, vulture, check_file_size) — fix all issues
- [x] Commit message prepared

### Step 5: Config — `core.config.LLMConfig` and `adapters.config` reader / loader — [step_5.md](./steps/step_5.md)
- [x] Implementation: tests first, then `core/config.py` and `adapters/config.py`
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports) — fix all issues
- [x] Commit message prepared

### Step 6: Public LLM functions in `adapters/llm.py` — [step_6.md](./steps/step_6.md)
- [x] Implementation: tests first, then `create_chat_model`, `map_provider_error`, `invoke`
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports) — fix all issues
- [x] Commit message prepared

### Step 7: Logging setup in `services/logging_setup.py` — [step_7.md](./steps/step_7.md)
- [x] Implementation: tests first, then `setup_logging` / `LOG_LEVELS`, `.importlinter` services entry
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports) — fix all issues
- [x] Commit message prepared

### Step 8: `verify` checks and exit code in `services/verify.py` — [step_8.md](./steps/step_8.md)
- [x] Implementation: tests first, then `VerifyReport`, `verify_config`, `collect_install_hints`, `compute_exit_code`, `run_verify`
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach) — fix all issues
- [x] Commit message prepared

### Step 9: CLI `verify` / `prompt` subcommands, formatter, placeholder removal — [step_9.md](./steps/step_9.md)
- [x] Implementation: tests first, then `cli.py` rewrite, `verify_formatting.py`, greeting removal, integration test
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture) — fix all issues
- [x] Commit message prepared

### Step 10: Docs (README, architecture.md, CLAUDE.md pytest note) — [step_10.md](./steps/step_10.md)
- [x] Implementation: update `README.md`, `docs/architecture/architecture.md`, `.claude/CLAUDE.md`
- [x] Quality checks: pylint, pytest, mypy (plus ruff, lint-imports, tach, vulture, deptry, bandit, check_file_size) — fix all issues
- [x] Commit message prepared

## Pull Request
- [ ] PR review: review the full branch diff against `main`, address findings
- [ ] PR summary prepared (include `pr_info/pr_notes.md` content: skipped copied tests, dropped import-linter entries)
