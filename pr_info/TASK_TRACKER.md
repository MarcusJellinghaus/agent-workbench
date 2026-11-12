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

### Step 1: mypy overrides for the tool packages - [step_1.md](./steps/step_1.md)
- [x] Implementation: mypy overrides for `mcp_tools_sql` / `mcp_workspace` in `pyproject.toml`
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `mcp_coder_utils` shims and tightened import contract - [step_2.md](./steps/step_2.md)
- [x] Implementation: `redaction` / `tool_spec` / `user_app_data` shims, shim imports in `config.py` and `_provider_checks.py`, `.importlinter` contracts, `tests/adapters/test_shims.py`
- [x] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [x] Commit message prepared

### Step 3: App log for the UI and clamped sibling loggers - [step_3.md](./steps/step_3.md)
- [x] Implementation: `setup_logging(log_file, console_level)` with sibling clamp, `app_log_file`, launcher default `INFO`, `restore_root_logging` fixture in `tests/conftest.py`, tests
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 4: `[tools]` config reading and validation - [step_4.md](./steps/step_4.md)
- [x] Implementation: `ConfigFile.tools` / `tools_type_error`, `TOOL_KEYS`, `REQUIRED_TOOL_KEYS`, `tool_path`, `tools_config_problems`, tests
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 5: Result helper and `ToolSpec` → `StructuredTool` adapter - [step_5.md](./steps/step_5.md)
- [x] Implementation: `adapters/tool_results.py` (`result_text`), `adapters/tools.py` (`to_structured_tool`), tests
- [x] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [x] Commit message prepared

### Step 6: Tool-call log and `wrap_spec` - [step_6.md](./steps/step_6.md)
- [x] Implementation: `services/tool_call_log.py` (`truncate_text`, `sanitize_params`, `tool_call_log_path`, `log_tool_call`, `wrap_spec`), tests
- [x] Quality checks: pylint, pytest, mypy, lint-imports — fix all issues
- [x] Commit message prepared

### Step 7: Tool errors, tool callbacks and inactivity pause - [step_7.md](./steps/step_7.md)
- [x] Implementation: `handle_tool_errors=True` in `build_graph`, `on_tool_start` / `on_tool_end` callbacks and idle-timer pause in `run_turn`, tests
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 8: Remove the hard-coded tool packages - [step_8.md](./steps/step_8.md)
- [x] Implementation: revert the tool-package mypy override, remove `SIBLING_LOGGERS` and its clamp loop, remove `TOOL_KEYS` / `REQUIRED_TOOL_KEYS` / `tool_path` and the key checks (`tools_config_problems` → shape only), adjust tests
- [x] Quality checks: pylint, pytest, mypy, vulture — fix all issues
- [x] Commit message prepared

### Step 9: Toolset providers: entry-point discovery and `build_toolsets` - [step_9.md](./steps/step_9.md)
- [x] Implementation: `adapters/toolset_providers.py`, `Toolsets` / `build_toolsets`, shim re-exports, `tool_packages_isolation` contract, extras + DEP002 ignore, `tests/adapters/tool_fixtures.py` (fake provider), tests
- [x] Quality checks: pylint, pytest, mypy, lint-imports, deptry, `tools/check_no_url_deps.py` — fix all issues
- [x] Commit message prepared

### Step 10: Runtime wiring, tool filter, logger clamp, agent-loop and `mcp` tests - [step_10.md](./steps/step_10.md)
- [x] Implementation: `services/tool_filter.py`, `clamp_loggers`, `Runtime.toolsets`, `build_tools`, `get_runtime` / `close_runtime`, `test_tool_filter.py`, `test_agent_tools.py` (fake provider; real providers as integration), `tests/test_tool_path_no_mcp.py` (integration)
- [x] Quality checks: pylint, pytest, mypy, lint-imports, tach — fix all issues
- [x] Commit message prepared

### Step 11: Chainlit tool steps - [step_11.md](./steps/step_11.md)
- [x] Implementation: `ToolSteps` in `ui_handlers.py`, wiring in `on_message` and `close_all` in `finally`, tests incl. end-to-end with a fake provider
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 12: Launcher gate: build and close the toolsets before Chainlit - [step_12.md](./steps/step_12.md)
- [x] Implementation: `_check_toolsets` (logger clamp, build, close) and gate in `ui_launcher.main`, tests
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 13: `verify` TOOLS section with the providers' rows - [step_13.md](./steps/step_13.md)
- [x] Implementation: `verify_tools(connect=...)`, `run_verify(connect_tools=...)`, `VerifyReport` fields, `compute_exit_code`, TOOLS section in `verify_formatting`, launcher passes `connect_tools=False`, tests
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 14: Documentation - [step_14.md](./steps/step_14.md)
- [ ] Implementation: `README.md`, `docs/architecture/architecture.md`, `docs/security/security_design.md`
- [ ] Quality checks: pytest — fix all issues
- [ ] Commit message prepared

## Pull Request
- [ ] PR review: review the full branch diff and address the findings
- [ ] PR summary prepared (incl. the manual smoke test: model lists tables and writes a markdown report)
