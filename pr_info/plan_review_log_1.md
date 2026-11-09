# review-plan review log 1

## Round 1 — 2026-11-09
**Findings**:
Reviewing plan files against the repo; checking `.importlinter` and a few source facts next.`pr_info/steps/step_4.md:31` — high — Step 4 adds `ignore_imports = agent_workbench.apps.** -> langchain_core` to `langchain_core_isolation`, but no `apps` module imports `langchain_core` directly in step 4: `build_graph` uses only `langgraph`. The installed import-linter defaults `unmatched_ignore_imports_alerting` to `ERROR`, so lint-imports will fail and break step 4's one-commit exit criteria. Fix: add the ignore in the step where an `apps` module first imports `langchain_core` directly, or set `unmatched_ignore_imports_alerting = none` on that contract.

`pr_info/steps/step_5.md:46` — high — Step 5 leaves open whether the input is built with `HumanMessage` or `[("user", text)]` (no import). With `("user", text)`, no `apps` module ever imports `langchain_core`, so the ignore required by the issue stays unmatched for the whole PR and lint-imports fails. Pick one: use `HumanMessage` (or an `AIMessage` check in the fallback) and move the contract change here, or drop the tuple option.

`pr_info/steps/step_5.md:53` — low — `NodeCancelledError` is imported inside `try/except ImportError`, and the test at line 94 is skipped when the class is missing. `knowledge_base/python.md` says to avoid conditional imports. The `langgraph>=1.2.9` floor fixes whether the class exists: probe for it and import it unconditionally, or drop the branch if the class does not exist at that floor.

`pr_info/steps/step_9.md:63` — low — No handler test covers Stop: that `on_message` lets a `CancelledError` from `run_turn` propagate and sends no message of its own. The acceptance criterion "Stop cancels the turn and the app adds no message" is tested only at the `run_turn` level, while the "no message" behaviour belongs to the handler.
**Decisions**:
Verdict(decision='tasks', tasks=['pr_info/steps/step_4.md:31 and pr_info/steps/step_5.md:46: Make step 5 build the agent input with `HumanMessage` from `langchain_core` and remove the `[("user", text)]` tuple option. Move the `ignore_imports = agent_workbench.apps.** -> langchain_core` addition to the `langchain_core_isolation` contract out of step 4 and into step 5, where an `apps` module first imports `langchain_core`. Lint-imports must then pass at the end of each step.', 'pr_info/steps/step_5.md:53: Remove the `try/except ImportError` around the `NodeCancelledError` import, and the matching conditional skip in the test at line 94. Check whether the class exists at the `langgraph>=1.2.9` floor. If it does, import it unconditionally. If it does not, drop that branch and its test.', 'pr_info/steps/step_9.md:63: Add a handler-level test for Stop. When `run_turn` raises `CancelledError`, `on_message` must let it propagate and must not send any message of its own.'], escalate_reason=None)
**Changes**:
applied
