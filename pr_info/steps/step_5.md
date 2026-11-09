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
- Create `tests/apps/test_agent_turn.py`

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
- Input: `{"messages": [HumanMessage(content=text)]}` – or `[("user", text)]`, which needs
  no `langchain_core` import.
- Delta text: `chunk.text` (property in langchain-core ≥ 1.0; covers list content).
- Usage: `usage = llm.add_usage(usage, event["data"]["output"])` per `on_chat_model_end`;
  `token_usage.update(input, output, cache_read)` only after the stream completed.
- `map_provider_error` raises (NoReturn): call it via `asyncio.to_thread` inside a
  `try/except Exception as mapped` and use `mapped` for the message.
- `NodeCancelledError`: `from langgraph.errors import NodeCancelledError` guarded by
  `try/except ImportError`, as mcp_coder's `_is_node_cancelled`.
- Never `except BaseException`; `asyncio.CancelledError` propagates; the function adds no
  message on Stop.
- Close the event stream on exit (`contextlib.aclosing`).

## ALGORITHM
```
usage, streamed = {}, False; cm = asyncio.timeout(overall_timeout)
try:
  async with cm, aclosing(graph.astream_events(input, run_config, version="v2")) as events:
    while (event := await wait_for(anext(events, _END), idle_timeout)) is not _END:
      stream event → on_text(delta), streamed = True;  end event → usage = add_usage(usage, output)
  if not streamed: on_text(last AIMessage text from await graph.aget_state(run_config))
  token_usage.update(...); return None
except TimeoutError: return OVERALL if cm.expired() else IDLE
except GraphRecursionError: return STEPS
except Exception as exc: NodeCancelled → raise CancelledError from exc; else map in thread → "Error: …"
```

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
  event; `idle_timeout=0.05` → idle message.
- Overall timeout: same stalling model, `idle_timeout=5`, `overall_timeout=0.05` → overall message.
- Stop: start `run_turn` as a task with the stalling model, wait until it is inside
  `_agenerate`, cancel → `CancelledError` raised, `on_text` not called, `map_provider_error`
  (patched spy) not called.
- `NodeCancelledError`: model raising `asyncio.CancelledError` from `_agenerate` →
  `run_turn` raises `CancelledError` (skip if the installed langgraph lacks the class).
- Usage: scripted messages with `usage_metadata` → per-turn sum (two model calls in one
  turn, via a tool call), session total over two turns; a failed turn leaves `token_usage`
  unchanged.

## Checks / commit
pylint, pytest, mypy, ruff, lint-imports, vulture. Commit:
`feat(apps): agent turn with streaming, limits and token usage`.
