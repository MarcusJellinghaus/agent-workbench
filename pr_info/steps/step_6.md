# Step 6 – Per-turn wiring in `run_turn`: `TurnPermissions`, timer pause during a dialog

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`), and issue #18
(Scope "Per-turn wiring", Constraints "The dialog runs before `on_tool_start`" and "The
callback must not be persisted"). Implement step 6 only, test first. Run pylint, pytest
(`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and lint-imports until all
pass. One commit.

## WHERE
- `src/agent_workbench/apps/agent.py` (`run_turn`)
- Tests: `tests/apps/test_agent_turn.py` (or `tests/apps/test_permission_gate.py` for the
  graph-level ones if `test_agent_turn.py` would pass 750 lines)

## WHAT
```python
async def run_turn(..., on_tool_end: ToolEnd | None = None,
                   confirm: Confirm | None = None,
                   grants: set[str] | None = None) -> str | None:
```
- `confirm` given → `configurable[TURN_PERMISSIONS_KEY] = TurnPermissions(paused_confirm,
  grants if grants is not None else set(), asyncio.Lock())` – one object, one key, never
  rebound. `confirm` None → no key → `ask` / `ask_session` fail closed.
- Docstring: the inactivity limit is also paused while a dialog is open; new args.

## ALGORITHM
```
tool_paused = False; dialogs_open = 0
def rearm():   # never touch an expired timer: its TimeoutError must win
    if not idle.expired(): idle.reschedule(None if tool_paused or dialogs_open else loop.time() + idle_timeout)
async def paused_confirm(name, args, mode):
    nonlocal dialogs_open; dialogs_open += 1; rearm()
    try: return await confirm(name, args, mode)
    finally: dialogs_open -= 1; rearm()
event loop: on_tool_start → tool_paused = True; on_chat_model_start → tool_paused = False; rearm()
```
The end of a dialog must not re-arm the timer while an approved tool still runs
(`tool_paused`). The overall limit is unchanged. If pylint flags `run_turn` (locals /
statements), move the timer state into a small private class in `agent.py` with the same
behaviour.

## HOW
`from agent_workbench.apps.permission_gate import TURN_PERMISSIONS_KEY, Confirm, TurnPermissions`.
The lock is per turn; grants come from the caller (the Chainlit session in step 7).

## DATA
`run_config["configurable"]`: `{"thread_id": str, TURN_PERMISSIONS_KEY: TurnPermissions}`.

## Tests (write first)
Scripted fake model, fake specs; build `Toolsets` directly with hand-written specs when a
tool must await an `asyncio.Event` (see `tests/adapters/tool_fixtures.py` for `tool_spec`):
- a dialog open longer than `idle_timeout` (e.g. 0.05 s timeout, confirm sleeps 0.3 s) → turn
  returns None and the tool ran.
- a dialog ends while an approved tool is still running (call A `ask` approved, its tool
  waits; call B `ask` dialog closes while A runs; A finishes after > `idle_timeout`) → no
  idle error.
- `confirm` None → an `ask` tool is denied with `DENY_UNAVAILABLE`, outcome `denied`.
- confirm receives `(name, args, mode)`; the passed `grants` set is the one the gate fills
  (`ask_session` OK → name in `grants` after the turn).
- the callback is not stored in the checkpoint: after a turn with `InMemorySaver`,
  `(await saver.aget_tuple(cfg)).metadata` has no `TURN_PERMISSIONS_KEY` and no callable value.
- Stop (cancel the `run_turn` task) during a dialog → `CancelledError`, outcome `cancelled`.
