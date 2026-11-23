# Step 7 – Chainlit dialog and `ask_session` grants in `ui_handlers`

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_7.md`), and issue #18
(Scope "Dialog" and "Per-turn wiring", Decisions "Dialog content", "Grant storage").
Implement step 7 only, test first. Run pylint, pytest
(`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and lint-imports until all
pass. One commit.

Precondition: the installed Chainlit has `cl.AskActionMessage(content, actions, timeout=...)`,
`cl.Action(name, payload, label)` and `context.emitter.clear("clear_ask")`. If not, write
one line to `pr_info/.blocked.txt` and stop.

## WHERE
- `src/agent_workbench/apps/ui_handlers.py`
- Tests: new `tests/apps/test_ui_handlers_dialog.py`; `tests/apps/test_ui_handlers.py`
  (`on_message` / `on_chat_resume` wiring)

## WHAT
```python
DIALOG_TIMEOUT = 300  # seconds; a timeout counts as Cancel
GRANTS_KEY = "permission_grants"

def arguments_markdown(name: str, args: dict[str, Any]) -> str:
    """Tool name plus the full arguments as JSON in a code fence no backtick run can close."""

async def confirm_tool_call(name: str, args: dict[str, Any], mode: PermissionMode) -> bool:
    """Send the arguments message, then OK / Cancel; True only for OK."""

async def _cancel_ask(ask: cl.AskActionMessage) -> None:
    """Remove the buttons, clear the ask, mark its text cancelled; logs, never raises."""

def _session_grants() -> set[str]:
    """The conversation's ask_session grants (a set in cl.user_session, created if missing)."""
```

## ALGORITHM
`arguments_markdown`:
```
text = json.dumps(args, indent=2, ensure_ascii=False, default=str)
longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
fence = "`" * max(3, longest + 1)
return f"Tool call **{name}** with these arguments:\n\n{fence}json\n{text}\n{fence}"
```
`confirm_tool_call`:
```
await cl.Message(content=arguments_markdown(name, args)).send()   # stays visible and stored
text = f"Allow **{name}**?" + (" OK allows this tool for the rest of the conversation." if mode == "ask_session" else "")
ask = cl.AskActionMessage(content=text, actions=[Action("ok", {}, "OK"), Action("cancel", {}, "Cancel")], timeout=DIALOG_TIMEOUT)
try: res = await ask.send()
except asyncio.CancelledError: await _cancel_ask(ask); raise
return res is not None and res.get("name") == "ok"                # None (timeout) = Cancel
```
`_cancel_ask`: `for a in ask.actions: await a.remove()`; `await cl.context.emitter.clear("clear_ask")`;
`ask.content = "Cancelled – the tool call did not run."`; `ask.wait_for_answer = False`;
`await ask.update()`; any `Exception` → `logger.exception`. Needed because Chainlit's
`send_ask_user` skips this cleanup on cancel.

## HOW
- `on_message`: pass `confirm=confirm_tool_call, grants=_session_grants()` to `run_turn`.
- `_session_grants`: `grants = cl.user_session.get(GRANTS_KEY)`; if not a `set`, create
  `set()` and `cl.user_session.set(GRANTS_KEY, grants)` (a restored `null` is replaced).
- `on_chat_resume`: first statement, before and outside its `try`:
  `cl.user_session.set(GRANTS_KEY, set())` – a resume asks again.
- A new chat or page reload gets a new user session, hence a new set.

## DATA
`confirm_tool_call` returns `bool`; grants are a `set[str]` of tool names.

## Tests (write first)
`tests/apps/test_ui_handlers_dialog.py` (with the `fake_cl` pattern of `test_ui_handlers.py`
for message order; a real Chainlit context for the cancel test):
- the arguments message is sent before the ask; its content holds the tool name and the JSON.
- arguments containing ```` ``` ```` and longer backtick runs stay inside the fence (the fence
  is longer than the longest run; the text after the closing fence is empty).
- `ask_session` text says OK applies for the rest of the conversation; `ask` text does not.
- `timeout == 300`; answer OK → True; Cancel → False; `None` → False.
- Stop during the dialog, run through `agent.run_turn` with a real graph and a fake emitter:
  set `chainlit.context.context_var` to a `ChainlitContext` whose emitter subclasses
  `BaseChainlitEmitter`, records `emit` / `clear` / `update_step` calls, and whose
  `send_ask_user` waits forever; cancel the turn task → `CancelledError`, `remove_action`
  emitted for both actions, `clear("clear_ask")` called, the ask's updated content says
  cancelled, outcome `cancelled` logged.
`tests/apps/test_ui_handlers.py`:
- `on_message` passes `confirm_tool_call` and the session's grants set; a second turn in the
  same session gets the same set; a fresh session gets a new set.
- `on_chat_resume` replaces the grants with an empty set, also when `get_runtime` fails.
