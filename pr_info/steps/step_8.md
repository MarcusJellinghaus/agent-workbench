# Step 8 – Tool errors, tool callbacks and inactivity pause

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_8.md`), then implement
this step only. TDD: tests first. Run pylint, pytest (`-n auto -m "not integration"`) and
mypy; all must pass. One commit.

## WHERE
- `src/agent_workbench/apps/agent.py` (`build_graph`, `run_turn`)
- `tests/apps/test_agent_graph.py`, `tests/apps/test_agent_turn.py`

## WHAT
```python
ToolStart = Callable[[str, str, dict[str, Any]], Awaitable[None]]  # run_id, tool name, args
ToolEnd = Callable[[str, str], Awaitable[None]]                    # run_id, output text

async def run_turn(  # existing parameters unchanged
    ...,
    *,
    idle_timeout: float = IDLE_TIMEOUT,
    overall_timeout: float = OVERALL_TIMEOUT,
    on_tool_start: ToolStart | None = None,
    on_tool_end: ToolEnd | None = None,
) -> str | None: ...
```

## HOW
- `build_graph`: `ToolNode(list(tools), handle_tool_errors=True)` with a comment: the
  default handler re-raises everything except `ToolInvocationError`; with `True` every
  tool exception becomes an error `ToolMessage` (its text goes to the provider) and the
  turn continues. `asyncio.CancelledError` is not an `Exception` and still propagates.
- `run_turn`, inside the existing `astream_events` loop:
  - `on_tool_start` event → `paused = True`; call `on_tool_start(event["run_id"],
    event["name"], event["data"].get("input") or {})`.
  - `on_tool_end` and `on_tool_error` events → call `on_tool_end(run_id, text)` with
    `text = str(getattr(output, "content", output))` (error: `str(event["data"].get("error"))`).
    Find out which of the two a failed tool emits with `handle_tool_errors=True` and note
    it in a comment; the UI closes leftover steps anyway (step 10).
  - `on_chat_model_start` → `paused = False`.
  - Timer: `idle.reschedule(None if paused else loop.time() + idle_timeout)` on every
    event. Resuming does not depend on a tool-end event. The overall timer still applies.
- Docstring: document the callbacks and the pause (the inactivity limit is per model call).

## ALGORITHM
```
paused = False
async for event in events:
    kind = event["event"]
    if kind == "on_tool_start": paused = True; await on_tool_start?(...)
    elif kind == "on_chat_model_start": paused = False
    idle.reschedule(None if paused else loop.time() + idle_timeout)
    ... existing stream / usage handling; tool end/error → await on_tool_end?(...)
```

## Tests
- `test_agent_graph.py`: a `StructuredTool` raising `ValueError("boom")`; scripted model
  calls it, then answers "done" → `ToolMessage.status == "error"`, content contains
  `boom`, last message "done", model invoked twice.
- `test_agent_turn.py` (scripted model from `tests/langchain_doubles.py`, `InMemorySaver`):
  - async tool sleeping 0.3 s, `idle_timeout=0.1`, `overall_timeout=5` → `run_turn`
    returns `None` and the final answer is streamed (no "No response from the model").
  - a stalling model after a tool still hits the idle limit (pause ended at
    `on_chat_model_start`).
  - callbacks: one tool call → `on_tool_start` once with name and args, `on_tool_end`
    once with the same `run_id` and the tool's text.
  - failing tool: turn returns `None`; record which callbacks fired (the assertion
    documents the emitted event).
  - Stop while a tool awaits → `asyncio.CancelledError` propagates.

## DATA
Callbacks receive `run_id: str`, `name: str`, `args: dict`, `output: str`.
