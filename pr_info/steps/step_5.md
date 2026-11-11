# Step 5 – Result helper and `ToolSpec` → `StructuredTool` adapter

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`), then implement
this step only. TDD: tests first. Run pylint, pytest (`-n auto -m "not integration"`), mypy
and lint-imports; all must pass. One commit.

## WHERE
- new `src/agent_workbench/adapters/tool_results.py` (must not import `langchain_core`)
- new `src/agent_workbench/adapters/tools.py`
- new `tests/adapters/test_tool_results.py`, `tests/adapters/test_tools.py`

## WHAT
```python
# adapters/tool_results.py
def result_text(result: Any) -> str:
    """Return the text the model receives for a tool result.

    ``str`` passes through; everything else (dict, list – also ``list[str]`` and empty
    lists – bool, …) becomes JSON. LangChain would pass a ``list[str]`` on as content
    blocks.
    """

# adapters/tools.py
def to_structured_tool(spec: "ToolSpec") -> StructuredTool:
    """Return *spec* as a LangChain tool; a sync ``fn`` runs in LangChain's executor."""
```

## HOW
- `tools.py` module docstring: tool packages are imported only inside `build_toolsets`
  (step 6); `ToolSpec` only under `TYPE_CHECKING` (from `agent_workbench.adapters.tool_spec`).
  *(Plugin model: step 9 rewrites this docstring – tool packages are never imported,
  providers are loaded by entry point.)*
- `from langchain_core.tools import StructuredTool` at module level (adapters may).
- Sync `fn` → `StructuredTool(name=..., description=..., args_schema=spec.args_model,
  func=_call)`; async `fn` (`inspect.iscoroutinefunction`) → `coroutine=_acall`. The graph
  invokes tools only asynchronously, so a sync tool goes through LangChain's executor.

## ALGORITHM
```
result_text(r): return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False, default=str)

to_structured_tool(spec):
    if iscoroutinefunction(spec.fn):
        async def _acall(**kw): return result_text(await spec.fn(**kw))
        return StructuredTool(name, description, args_schema=spec.args_model, coroutine=_acall)
    def _call(**kw): return result_text(spec.fn(**kw))
    return StructuredTool(name, description, args_schema=spec.args_model, func=_call)
```

## Tests
Build specs in tests with `mcp_coder_utils.tool_spec.tool_spec(fn, group=..., read_only=...)`
(tests are outside the import contract).
- `test_tool_results.py` (parametrized): `"x"` → `"x"`; `{"a": 1}`, `["a", "b"]`, `[]`,
  `True`, `None`, a non-ASCII string inside a dict (kept, not escaped), a `Path` value
  (via `default=str`).
- `test_tools.py`:
  - sync and async specs: `await tool.ainvoke({"type": "tool_call", "name": n,
    "args": {...}, "id": "c1"})` returns a `ToolMessage` whose `content` is the expected
    string; parametrize results dict / `list[str]` / `[]` / bool → JSON text.
  - name, description and `args_schema is spec.args_model` carried over.
  - invalid arguments raise (pydantic validation through `args_schema`).

## DATA
`result_text` → `str`; `to_structured_tool` → `StructuredTool`.
