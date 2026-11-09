# Step 4 – Agent graph and runtime getter

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 4: add `langgraph`, copy
mcp_coder's fake chat model, and create `apps/agent.py` with `build_graph` and
`get_runtime`. Tests first, then code; all checks pass; one commit.

## Precondition
`langgraph` and `langchain_core` must be resolvable
(`search_library_files(scope=..., glob="__init__.py")`). Otherwise write one line to
`pr_info/.blocked.txt` and stop.

## WHERE
- Modify `pyproject.toml`, `.importlinter`, `vulture_whitelist.py`
- Create `tests/langchain_doubles.py` (verbatim copy, not edited afterwards)
- Create `src/agent_workbench/apps/agent.py`
- Create `tests/apps/__init__.py`, `tests/apps/test_agent_graph.py`

## Packaging / contracts
- Already done ahead of this step: `"langgraph>=1.2.9"` in `[langchain-base]` and the
  `langgraph` mypy override. Remove `langgraph` from `[tool.deptry.per_rule_ignores]
  DEP002` (the import added here makes it used).
- `.importlinter`: new `langgraph_isolation` contract (forbidden `langgraph` from
  `agent_workbench`, `ignore_imports = agent_workbench.apps.** -> langgraph`), comment
  "langgraph: the agent graph. Allowed in apps only." `langchain_core_isolation` stays
  unchanged here: no `apps` module imports `langchain_core` yet, and import-linter fails on
  an unmatched ignore (`unmatched_ignore_imports_alerting` defaults to `error`). Step 5 adds it.

## WHAT (`apps/agent.py`)
```python
AGENT_MAX_STEPS = 50          # mcp_coder AGENT_MAX_STEPS
MODEL_TIMEOUT = 300           # HTTP timeout of the chat model (ICODER_LLM_TIMEOUT_SECONDS)

def build_graph(chat_model: Any, tools: Sequence[Any], checkpointer: Any) -> Any:
    """Compile model node → ToolNode, routed by tools_condition."""

@dataclass(frozen=True)
class Runtime:
    graph: Any
    chat_model: Any
    llm_config: LLMConfig

async def get_runtime() -> Runtime:
    """Process-wide runtime, created on first call (#16 swaps the saver here)."""
```

## HOW
- Top-level imports from `langgraph` are fine in `agent.py` (the launcher never imports it
  at module level). No Chainlit import.
- `get_runtime`: module-level `_runtime: Runtime | None = None`; config from
  `adapters.config.load_llm_config()`, model from
  `adapters.llm.create_chat_model(config, MODEL_TIMEOUT)`, saver
  `langgraph.checkpoint.memory.InMemorySaver()`, tools `[]`. No `asyncio.Lock`: nothing
  awaits while building, so it is race-free; comment that #16 adds a lock with the async
  SQLite saver.
- No system prompt.
- Probe (`.scratch/`): `ToolNode([])` is accepted; `tools_condition` routes to the node
  named `"tools"`. Delete `.scratch/` afterwards.

## ALGORITHM (`build_graph`)
```
model = chat_model.bind_tools(tools) if tools else chat_model
async def call_model(state: MessagesState) -> dict: return {"messages": [await model.ainvoke(state["messages"])]}
g = StateGraph(MessagesState); g.add_node("model", call_model); g.add_node("tools", ToolNode(list(tools)))
g.add_edge(START, "model"); g.add_conditional_edges("model", tools_condition); g.add_edge("tools", "model")
return g.compile(checkpointer=checkpointer)
```

## DATA
`Runtime(graph, chat_model, llm_config)`.

## Tests
- `tests/langchain_doubles.py`: verbatim copy of `033a9d05:tests/langchain_doubles.py`
  with the header `# Copied from mcp_coder tests/langchain_doubles.py at commit 033a9d05.`
- `tests/apps/test_agent_graph.py` (fake from `make_scripted_chat_model`, `InMemorySaver`):
  - empty tool list → `bind_tools` not called (`patch.object(type(model), "bind_tools")` spy);
  - non-empty tool list → `bind_tools` called once with the tools;
  - a scripted `AIMessage` with a `tool_calls` entry for an unknown tool → the graph routes
    to `ToolNode`, which answers with an error `ToolMessage`; the next scripted answer ends
    the run;
  - `get_runtime()` with `load_llm_config` / `create_chat_model` patched (monkeypatch
    `agent._runtime` to `None`) → second call returns the same object, the model is built
    once with `MODEL_TIMEOUT`.

## Vulture
Whitelist whatever vulture reports in `tests/langchain_doubles.py` (e.g. `_generate`,
`_agenerate`, `_llm_type`, `bind_tools`), comment
`tests/langchain_doubles.py: BaseChatModel overrides of the copied fake, called by langchain_core`.

## Checks / commit
pylint, pytest, mypy, ruff, lint-imports, vulture, deptry (langgraph is now imported from
`src`), tach. Commit: `feat(apps): LangGraph agent graph and runtime getter`.
