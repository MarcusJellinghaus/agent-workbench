# review-plan review log 1

## Round 1 — 2026-11-11
**Findings**:
Now steps and linked issues.Reviewing the #17 plan: read the issue, the epic, all 13 step files and the current code. Now checking the sibling package APIs the plan relies on.Verifying the SQL schema tool names the plan's binding test hard-codes, then a few remaining code checks.pr_info/steps/step_1.md:41 — medium — Step 1 adds the `sql`, `sql-mssql` and `workspace` extras, but nothing in `src` imports `mcp_tools_sql` or `mcp_workspace` until step 6. deptry treats these non-dev extras as runtime dependencies and reports DEP002 for both. `mcp-workspace` also leaves the dev-only exemption once it is in `workspace`. So the step's own deptry check and the CI `deptry` job fail on this commit. Fix: move the extras (and the `dev` / install-from-github entries) to step 6, where the first import lands.

pr_info/steps/step_9.md:45 — medium — `get_runtime` builds the toolsets only `if config_file.tools`. A non-table `[tools]` value sets `tools={}` plus `tools_type_error`, so the build is skipped and the model silently gets no tools. The issue says a broken `[tools]` config makes the build in `get_runtime` fail, and its decisions rule out a silent fallback. Use `config_file.tools or config_file.tools_type_error` (`build_toolsets` already raises on that error). Change the same condition in `pr_info/steps/step_11.md:40`.

pr_info/steps/step_9.md:69 — low — The acceptance criterion asks for one agent-loop test with real tools that also opens and closes a Chainlit tool step. The plan splits this: recorded callbacks here, and `ToolSteps` driven by a fake `run_turn` in step 10. No test feeds real `run_turn` tool events into `ToolSteps`. Add one in step 10, or state in step 9 that the split covers the criterion.

pr_info/steps/step_9.md:88 — low — "`env` with `PYTHONPATH=src`" can be read as a fresh environment dict. On Windows, a subprocess without `SYSTEMROOT` and the rest of `os.environ` can fail to start Python. Specify `{**os.environ, "PYTHONPATH": "src"}`.

pr_info/steps/step_9.md:10 — low — Step 9 bundles a new module (`tool_filter`), the runtime wiring and three new test files, one of them a subprocess test, into one commit. Move `tool_filter` and its test to step 7, or the subprocess test to its own step, to keep each step small enough for one TDD commit.

pr_info/steps/step_3.md:30 — low — The issue says that if a step needs something `log_utils` cannot do (beyond the JSONL exception), implementation stops and reports. This rule appears in no step prompt. Add it to the LLM prompt of step 3 (and of step 7, which is the documented exception).
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_1.md:41 — Move the `sql`, `sql-mssql` and `workspace` extras, plus their `dev` and install-from-github entries, out of step 1 and into step 6, where `src` first imports `mcp_tools_sql` / `mcp_workspace`. Otherwise deptry reports DEP002 and the CI deptry job fails on the step 1 commit.', 'pr_info/steps/step_9.md:45 — Change the `get_runtime` toolset-build condition from `if config_file.tools` to `if config_file.tools or config_file.tools_type_error`, so a non-table `[tools]` value reaches `build_toolsets` and raises instead of silently giving the model no tools. Make the same change in pr_info/steps/step_11.md:40, and add or keep a test asserting that a non-table `[tools]` makes `get_runtime` fail.', "pr_info/steps/step_10.md — Add one test that feeds the tool events from the real `run_turn` (with real tools, as in step 9) into `ToolSteps` and asserts a Chainlit tool step opens and closes. This covers the issue's single end-to-end acceptance criterion. Reference this test from pr_info/steps/step_9.md:69.", 'pr_info/steps/step_9.md:88 — Specify the subprocess environment as `{**os.environ, "PYTHONPATH": "src"}` rather than a fresh dict, so `SYSTEMROOT` and the rest of the environment are kept on Windows.', "pr_info/steps/step_3.md:30 and pr_info/steps/step_7.md — Add the issue's rule to each step's LLM prompt: if the step needs something `log_utils` cannot do (beyond the documented JSONL exception in step 7), stop and report instead of working around it."], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-11
**Findings**:
Now the step files.Still verifying the plan against the sibling package APIs; findings report follows.Checking `config_hints.unknown_key_hint` and the step-10 `on_message` wiring; report follows.pr_info/steps/step_1.md:21 — low — Step 1 now only adds a mypy override for packages nothing imports until step 6, so the commit has no testable result. The planning principles say to merge tiny steps. Fold the override into step 6, which edits `pyproject.toml` anyway, and renumber.
pr_info/steps/step_3.md:55 — low — The fixture that restores the root logging handlers is placed in `tests/services/test_logging_setup.py`. The `tests/apps/test_ui_launcher.py` test with the real `setup_logging` (line 69) needs it too, and pytest fixtures defined in one test module are not visible in another. Put it in `tests/conftest.py`, or in a shared helper that both files import.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_3.md:55 — Move the fixture that restores the root logging handlers out of `tests/services/test_logging_setup.py` and into `tests/conftest.py`, so the test in `tests/apps/test_ui_launcher.py` that uses the real `setup_logging` (step 3, line 69) can use it too. Update both step descriptions to match.'], escalate_reason=None)
**Changes**:
applied
