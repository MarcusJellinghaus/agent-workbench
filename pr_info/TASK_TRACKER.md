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

### Step 1: Permission model – mode type, `[permissions]` reader, parser / resolver, purity contract
See [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, lint-imports) – fix all issues
- [x] Commit message prepared

### Step 2: Move `Toolsets` / `build_toolsets` to `adapters/toolset_providers.py`; verify guard contract
See [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks (pylint, pytest, mypy, lint-imports, integration run of `tests/test_tool_path_no_mcp.py`) – fix all issues
- [x] Commit message prepared

### Step 3: PERMISSIONS section in `verify`; remove `ui_launcher._check_toolsets`
See [step_3.md](./steps/step_3.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports) – fix all issues
- [ ] Commit message prepared

### Step 4: Permission gate (`apps/permission_gate.py`) and `build_graph(..., modes=...)`
See [step_4.md](./steps/step_4.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports) – fix all issues
- [ ] Commit message prepared

### Step 5: Permissions drive binding and runtime; remove `services/tool_filter.py`
See [step_5.md](./steps/step_5.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports, integration run of `tests/test_tool_path_no_mcp.py`) – fix all issues
- [ ] Commit message prepared

### Step 6: Per-turn wiring in `run_turn` – `TurnPermissions`, timer pause while a dialog is open
See [step_6.md](./steps/step_6.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports) – fix all issues
- [ ] Commit message prepared

### Step 7: Chainlit dialog and `ask_session` grants in `ui_handlers`
See [step_7.md](./steps/step_7.md)

- [ ] Implementation (tests + production code)
- [ ] Quality checks (pylint, pytest, mypy, lint-imports) – fix all issues
- [ ] Commit message prepared

### Step 8: Docs – README, architecture, security design
See [step_8.md](./steps/step_8.md)

- [ ] Implementation (documentation only, no code)
- [ ] Quality checks (pytest) – fix all issues
- [ ] Commit message prepared

## Pull Request

- [ ] PR review: review the full branch diff against `main`, fix findings
- [ ] Manual smoke test documented (OK, Cancel, `ask_session`, Stop during a dialog, plus the issue's "Smoke test also checks" list)
- [ ] PR summary prepared
