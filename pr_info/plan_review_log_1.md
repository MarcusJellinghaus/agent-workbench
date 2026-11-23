# review-plan review log 1

## Round 1 — 2026-11-23
**Findings**:
Reviewing the plan against the langgraph `ToolNode` source and the current code; a few more checks before reporting.Checking whether tests isolate the app-data dir (gate logging in existing graph tests), then I'll emit the report.`pr_info/steps/step_4.md:92` — medium — After this step the gate writes `unknown_tool`, `blocked` and `denied` lines through `log_tool_call` → `config.app_data_dir()`. Existing graph tests such as `tests/apps/test_agent_graph.py::test_unknown_tool_call_routes_to_tool_node` don't patch app data, and no autouse fixture does either (`tests/apps/conftest.py`). Those tests would then append to the developer's real `~/.agent_workbench/logs/tool_calls.jsonl`. The step should require patching `app_data_dir` in every `build_graph` caller that reaches a path where the tool doesn't run, or add an autouse fixture.
`pr_info/steps/step_1.md:70` — low — The claim "every message starts with the key, so `format_config_section` renders the key as the row label" is wrong. `_looks_like_key` accepts only a plain identifier as the first token, so `"<key>: ..."` (trailing colon) and dotted group keys like `"sql.schema"` are rendered without a label. Either drop the colon from the message format or drop the claim.
`pr_info/steps/step_3.md:48` — low — `rows = problems + [row(...)]` mixes types: `parse_permissions` returns `ProblemRow` tuples `(label, status, message)`, but the PERMISSIONS entries are `{"label", "status", "value"}` dicts. The problems must be converted with `_row` first.
`pr_info/steps/step_1.md:65` — low — For a key that is both a tool name and a group name, the step doesn't say whether the entry is skipped. The neighbouring error cases say "skip". If it lands in `entries`, `mode_of` treats it as a tool-level entry in verify's info rows.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_4.md (around line 92), require test isolation for gate audit logging: add an autouse fixture in tests/apps/conftest.py that patches `config.app_data_dir` to a tmp_path, so no graph test (e.g. test_unknown_tool_call_routes_to_tool_node) writes to the real ~/.agent_workbench/logs/tool_calls.jsonl.', 'In pr_info/steps/step_1.md (around line 70), make the message format match `_looks_like_key`. Either change the problem messages so they start with the bare key and no trailing colon, and state how dotted group keys are labelled, or remove the claim that format_config_section renders the key as the row label.', 'In pr_info/steps/step_3.md (around line 48), convert the `ProblemRow` tuples returned by `parse_permissions` with `_row(...)` before concatenating them with the PERMISSIONS dict rows, so `rows` holds only `{label, status, value}` dicts.', 'In pr_info/steps/step_1.md (around line 65), specify how a key that is both a tool name and a group name is handled: report it as a problem and skip it, like the other error cases, so it never lands in `entries` or gets treated as a tool-level entry by `mode_of`.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-23
**Findings**:
Reviewing the plan against the code: checking langgraph's `ToolNode`/`ToolCallRequest` API and the current verify/tool modules next.Checking `ui_handlers.py` and the test layout, then writing the report.`pr_info/steps/step_2.md:38` — medium — `tests/test_tool_path_no_mcp.py` is marked `@pytest.mark.integration`, and the import change goes into its `_SCRIPT` string. That string runs in a subprocess, so pylint, mypy and lint-imports never see it. The step's `-m "not integration"` pytest run never runs it either. A broken import would go unnoticed. The step should run `tests/test_tool_path_no_mcp.py` explicitly with `markers=["integration"]`; the test skips itself when the `sql`/`workspace` providers are missing.
`pr_info/steps/step_5.md:50` — medium — Same gap for the bigger `_SCRIPT` rewrite, which replaces `enabled_specs` with `parse_permissions` / `mode_of` and an inline `[permissions]` table. Nothing in the step's checks runs it. The step should run that test explicitly with `markers=["integration"]`, so the new script is checked to still build and call `read_tables` / `list_directory` and import no `mcp`.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_2.md (around line 38), add a verification step after the `_SCRIPT` import change that runs `tests/test_tool_path_no_mcp.py` explicitly with `markers=["integration"]`. Note that the test skips itself when the `sql`/`workspace` providers are missing.', 'In pr_info/steps/step_5.md (around line 50), add a verification step after the `_SCRIPT` rewrite (`parse_permissions` / `mode_of` plus the inline `[permissions]` table) that runs `tests/test_tool_path_no_mcp.py` explicitly with `markers=["integration"]`. It must confirm the script still builds, calls `read_tables` / `list_directory`, and imports no `mcp`.'], escalate_reason=None)
**Changes**:
applied

## Round 3 — 2026-11-23
**Findings**:
Reviewing plan against code: checking verify, ui_launcher and agent.run_turn next.Checking ToolNode's invalid-tool handling, then reporting.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
