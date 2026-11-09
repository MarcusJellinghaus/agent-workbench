# Step 5 – Turn function `run_turn`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 5: the Chainlit-free turn
function in `apps/agent.py` – streaming, final-message fallback, step limit, timeouts,
error mapping, Stop and token usage. Tests first, then code; all checks pass; one commit.

## Precondition
`langgraph` and `langchain_core` resolvable; otherwise write one line to
`pr_info/.blocked.txt` and stop.

## WHERE
- Modify `src/agent_workbench/apps/agent.py`
- Modify `.importlinter`
- Create `tests/apps/test_agent_turn.py`

## Contracts
`apps/agent.py` now imports `langchain_core` (`HumanMessage`) for the first time:
`langchain_core_isolation` gets `agent_workbench.apps.** -> langchain_core` in
`ignore_imports`, its name / comment say "adapters and apps". Added here, not earlier,
because import-linter fails on an unmatched ignore.

## WHAT
```python
IDLE_TIMEOUT = 300       # ICODER_LLM_TIMEOUT_SECONDS: no stream event for this long fails the turn
OVERALL_TIMEOUT = 3600   # _AGENT_OVERALL_TIMEOUT

async def run_turn(
    graph: Any,
    chat_model: Any,
    llm_config: LLMConfig,
    text: str,
    thread_id: str,
    on_text: Callable[[str], Awaitable[None]],
    token_usage: TokenUsage,
    *,
    idle_timeout: float = IDLE_TIMEOUT,
    overall_timeout: float = OVERALL_TIMEOUT,
) -> str | None:
    """Run one turn; stream text via *on_text*; return an error message or None."""
```
Module-level message texts (one place, used by tests):
`_IDLE_MSG = "No response from the model for {s} s – turn aborted."`,
`_OVERALL_MSG = "Turn exceeded {s} s – aborted."`,
`_STEPS_MSG = "Step limit of {n} reached – turn aborted. You can continue the conversation."`,
error: `f"Error: {mapped_exc}"`.

## HOW
- Pattern: mcp_coder `033a9d05:src/mcp_coder/llm/providers/langchain/agent.py`
  `run_agent_stream` (`astream_events(version="v2")`, `on_chat_model_stream`,
  `on_chat_model_end`, `_is_node_cancelled`) and `__init__.py` `_AGENT_OVERALL_TIMEOUT`.
- Run config: `{"configurable": {"thread_id": thread_id}, "recursion_limit": AGENT_MAX_STEPS}`.
- Input: `{"messages": [HumanMessage(content=text)]}` (`from langchain_core.messages import
  HumanMessage`, top level).
- Delta text: `chunk.text` (property in langchain-core ≥ 1.0; covers list content).
- Usage: `usage = llm.add_usage(usage, event["data"]["output"])` per `on_chat_model_end`;
  `token_usage.update(input, output, cache_read)` only after the stream completed.
- `map_provider_error` raises (NoReturn): call it via `asyncio.to_thread` inside a
  `try/except Exception as mapped` and use `mapped` for the message.
- `NodeCancelledError`: no `try/except ImportError` (`knowledge_base/python.md`). mcp_coder
  guards the import only because the class "exists in newer releases"; this step pins the
  answer for the `langgraph>=1.2.9` floor. Probe (`.scratch/`): does `langgraph.errors`
  define `NodeCancelledError` in 1.2.9? Read it from the installed source
  (`get_library_source("langgraph.errors")`) together with the installed version; if the
  installed version is newer than 1.2.9, check the 1.2.9 release (its changelog or source).
  - Present at 1.2.9 → top-level `from langgraph.errors import GraphRecursionError,
    NodeCancelledError`; re-raise as `asyncio.CancelledError`.
  - Absent at 1.2.9 → no `NodeCancelledError` branch and no test for it; note it in the PR.
- Never `except BaseException`; `asyncio.CancelledError` propagates; the function adds no
  message on Stop.
- Close the event stream on exit (`contextlib.aclosing`).
- Timeouts run inside the turn's own task, so cancelling a stalled model node can surface
  as langgraph's `NodeCancelledError` (an `Exception`) instead of `CancelledError`; then
  neither `asyncio.timeout` nor `wait_for` turns it into `TimeoutError`. mcp_coder avoids
  this only because its timeouts sit on the consumer side of a thread / queue. Hence:
  - idle timer = a second `asyncio.timeout` (no `wait_for`), rescheduled after every event
    (`idle.reschedule(loop.time() + idle_timeout)`), so `idle.expired()` tells whether it
    fired;
  - the `NodeCancelledError` branch checks `overall.expired()` and `idle.expired()` first
    and returns the matching timeout message; it re-raises `CancelledError` only when
    neither fired (Stop).
- Probe (`.scratch/`, before the tests), with a test-local model whose `_agenerate` awaits
  a never-set event, inside `build_graph(model, [], InMemorySaver())`:
  1. cancel the stalled node from outside via `asyncio.timeout` (overall-style) → record
     the exception `astream_events` raises (`CancelledError` or `NodeCancelledError`) and
     that `expired()` is True afterwards;
  2. the same via the rescheduled idle `asyncio.timeout` nested inside the overall one;
  3. `_agenerate` raising `asyncio.CancelledError` itself → record whether it comes out as
     `NodeCancelledError`.
  Note the results in the step's commit message body; the tests below rely on them.

## ALGORITHM
```
usage, streamed = {}, False
overall = asyncio.timeout(overall_timeout); idle = asyncio.timeout(idle_timeout)
try:
  async with overall, idle, aclosing(graph.astream_events(input, run_config, version="v2")) as events:
    async for event in events:
      idle.reschedule(loop.time() + idle_timeout)
      stream event → on_text(delta), streamed = True;  end event → usage = add_usage(usage, output)
  if not streamed: on_text(last AIMessage text from await graph.aget_state(run_config))
  token_usage.update(...); return None
except TimeoutError: return OVERALL if overall.expired() else IDLE
except GraphRecursionError: return STEPS
except NodeCancelledError as exc:                                  # only if present at 1.2.9
  if overall.expired(): return OVERALL
  if idle.expired(): return IDLE
  raise CancelledError from exc                                    # Stop
except Exception as exc: map in thread → "Error: …"
```
(`idle` covers only the event loop: `aget_state` and the fallback `on_text` run after it.)

## DATA
Returns `None` on success, else the user-facing message string. `token_usage` mutated only
on success.

## Tests (`tests/apps/test_agent_turn.py`)
Graph from `build_graph(model, [], InMemorySaver())`; `on_text` collects into a list.
- Plain answer: scripted fake (does not stream) → the final text arrives once via `on_text`.
- Second turn sees the first: after two turns on one `thread_id`, the checkpointer state
  (`await graph.aget_state(...)`) holds human/ai/human/ai, and the second model call's input
  (from the `on_chat_model_start` event or the state) contains the first exchange.
- Step limit: fake always returns a tool call → message contains "Step limit"; a following
  turn on the same thread still answers.
- Provider error: model raises; `adapters.llm.map_provider_error` patched to raise
  `RuntimeError("mapped")` → message `"Error: mapped"`; no vendor SDK loaded.
- Inactivity timeout: test-local `BaseChatModel` whose `_agenerate` awaits a never-set
  event; `idle_timeout=0.05` → idle message. Expected path (per the probe): stall in
  `_agenerate` → idle timer cancels → `NodeCancelledError` or `CancelledError`→`TimeoutError`
  → `idle.expired()` check → idle message. Asserts the idle message is returned (not a
  `CancelledError`) and `map_provider_error` (patched spy) is not called.
- Overall timeout: same stalling model, `idle_timeout=5`, `overall_timeout=0.05` → same
  path via `overall.expired()` → overall message; asserts the overall message, not a Stop.
- Stop: start `run_turn` as a task with the stalling model, wait until it is inside
  `_agenerate`, cancel → `CancelledError` raised, `on_text` not called, `map_provider_error`
  (patched spy) not called.
- `NodeCancelledError` (only if the probe found the class at 1.2.9; otherwise omitted, no
  skip): model raising `asyncio.CancelledError` from `_agenerate` (probe 3 confirmed it
  comes out as `NodeCancelledError`) → `run_turn` raises `CancelledError` whose
  `__cause__` is a `NodeCancelledError` (proves the re-raise branch ran);
  `map_provider_error` (patched spy) not called. If probe 3 shows no wrapping, raise
  `NodeCancelledError` from `_agenerate` directly instead.
- Usage: scripted messages with `usage_metadata` → per-turn sum (two model calls in one
  turn, via a tool call), session total over two turns; a failed turn leaves `token_usage`
  unchanged.

## Checks / commit
pylint, pytest, mypy, ruff, lint-imports, vulture. Commit:
`feat(apps): agent turn with streaming, limits and token usage`.
