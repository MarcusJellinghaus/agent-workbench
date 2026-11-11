# Step 10 – Chainlit tool steps

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_10.md`), then implement
this step only. Read `chainlit.step.Step` (`get_library_source`) for `send`, `update`,
`start` / `end` and `utc_now`. TDD: tests first. Run pylint, pytest
(`-n auto -m "not integration"`) and mypy; all must pass. One commit.

## WHERE
- `src/agent_workbench/apps/ui_handlers.py`
- `tests/apps/test_ui_handlers.py`

## WHAT
```python
TOOL_OUTPUT_CHARS = 2000  # characters of a tool result shown in its step

class ToolSteps:
    """The open ``cl.Step(type="tool")`` objects of one turn, by run id."""

    async def start(self, run_id: str, name: str, args: dict[str, Any]) -> None:
        """Open and send a tool step showing *args*."""

    async def end(self, run_id: str, output: str) -> None:
        """Set the truncated *output* and close the step (unknown run id: no-op)."""

    async def close_all(self) -> None:
        """Close every step still open; logs, never raises."""
```

## HOW
- `run_turn` stays free of Chainlit (rule in this module's docstring); `on_message`
  creates `steps = ToolSteps()` and passes `on_tool_start=steps.start`,
  `on_tool_end=steps.end` to `run_turn`.
- `on_message`'s `finally`: `await steps.close_all()` before `_finish_turn` – covers turn
  end, error and Stop (a failed tool may emit no end event).
- Step: `cl.Step(name=name, type="tool")`, `step.input = args`, `step.start = utc_now()`,
  `await step.send()`. End: `step.output = truncate_text(output, TOOL_OUTPUT_CHARS)`
  (from `agent_workbench.services.tool_call_log`), `step.end = utc_now()`,
  `await step.update()`. Steps are persisted by the data layer in `chainlit.sqlite`.
- Not `cl.LangchainCallbackHandler` (adds its own LLM steps and streaming).
- The existing handler tests fake `run_turn(*args)`; give the fakes `**kwargs`.

## ALGORITHM
```
start: step = cl.Step(name, type="tool"); step.input = args; step.start = utc_now(); await step.send(); open[run_id] = step
end:   step = open.pop(run_id, None); if step: step.output = truncate_text(output, N); step.end = utc_now(); await step.update()
close_all: for run_id in list(open): try: await end(run_id, "") except Exception: logger.exception(...)
```

## Tests (`tests/apps/test_ui_handlers.py`, `fake_cl` fixture: make `cl.Step` return a
`MagicMock` with `AsyncMock` `send` / `update`, recorded in a list)
- fake `run_turn` calls `on_tool_start("r1", "read_tables", {"schema": "main"})` and
  `on_tool_end("r1", "x" * 5000)` → one step, `type="tool"`, input set, sent once,
  output truncated to `TOOL_OUTPUT_CHARS` with length note, updated once.
- step started but not ended, turn returns → closed in `finally` (updated once).
- step open and the turn raises `asyncio.CancelledError` (Stop) → step closed,
  `CancelledError` still propagates.
- step open and `run_turn` returns an error message → step closed, error message sent.
- `update` raising in `close_all` → logged, `_finish_turn` still runs.
- end to end (issue acceptance criterion, agent-loop part in step 9): patch
  `agent_workbench.adapters.config.app_data_dir` → `tmp_path`; real `Toolsets` from
  `tests/adapters/tool_fixtures.py` (temp `database_config`) → `build_tools` →
  `build_graph` (`InMemorySaver`) with the scripted model calling `read_tables(schema="main")`, then
  answering "done"; the real `run_turn` with `on_tool_start=steps.start`,
  `on_tool_end=steps.end` of a `ToolSteps` (under `fake_cl`) → one step with
  `type="tool"` and name `read_tables`, sent once, output contains `customers`, updated
  once, none left open.

## DATA
`ToolSteps._open: dict[str, cl.Step]`.
