# Step 9 – Runtime wiring, tool filter, agent-loop and `mcp` subprocess tests

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_9.md`), then implement
this step only. Reference for the subprocess test: mcp-tools-sql
`tests/test_module_imports.py::test_toolset_does_not_import_mcp`. TDD: tests first. Run
pylint, pytest (`-n auto -m "not integration"`), mypy, lint-imports and tach; all must
pass. One commit.

## WHERE
- new `src/agent_workbench/services/tool_filter.py`
- `src/agent_workbench/apps/agent.py` (`Runtime`, `build_tools`, `get_runtime`, `close_runtime`)
- new `tests/services/test_tool_filter.py`
- new `tests/apps/test_agent_tools.py`
- new `tests/test_tool_path_no_mcp.py`
- `tests/apps/test_agent_graph.py` / `test_agent_checkpointer.py` (runtime tests, if needed)

## WHAT
```python
# services/tool_filter.py
ENABLED_GROUPS: frozenset[str] = frozenset({"sql.schema", "workspace.read", "workspace.write"})
ENABLED_TOOLS: frozenset[str] = frozenset({"validate_sql"})  # its group also holds `verify`

def enabled_specs(specs: Iterable["ToolSpec"]) -> tuple["ToolSpec", ...]:
    """Return the specs offered to the model until #18's permission resolver replaces this."""

# apps/agent.py
@dataclass(frozen=True)
class Runtime:
    graph: Any
    chat_model: Any
    llm_config: LLMConfig
    checkpointer: Any
    toolsets: Toolsets | None = None   # kept for #19's Reload

def build_tools(toolsets: Toolsets) -> list[Any]:
    """Return the enabled specs, logged and adapted, as LangChain tools."""
```

## HOW
- `build_tools`: `[to_structured_tool(wrap_spec(s)) for s in enabled_specs(toolsets.specs)]` –
  filtered before adapting, so non-enabled tools are never bound.
- `get_runtime`: `config_file = config.read_config_file()`;
  `llm_config = load_llm_config(config_file)`;
  `toolsets = build_toolsets(config_file) if config_file.tools or
  config_file.tools_type_error else None` (a non-table `[tools]` reaches
  `build_toolsets` and raises – no silent run without tools); then the
  checkpointer and the graph with `build_tools(toolsets) if toolsets else []`. Close what
  was opened if a later step fails.
- `close_runtime`: close the checkpointer connection in `try`, the toolsets in `finally`.

## ALGORITHM
```
toolsets = saver = None
try:
    toolsets = (
        build_toolsets(config_file)
        if config_file.tools or config_file.tools_type_error
        else None
    )
    saver = await open_checkpointer(...)
    graph = build_graph(chat_model, build_tools(toolsets) if toolsets else [], saver)
except BaseException:
    try: if saver: await saver.conn.close()
    finally: if toolsets: toolsets.close()
    raise
```

## Tests
- `test_tool_filter.py`: specs of groups `sql.schema`, `sql.validation` (`validate_sql`,
  `verify`), `sql.profiling`, `workspace.read`, `workspace.write`, `workspace.delete` →
  only schema, `validate_sql`, read and write remain, order kept.
- `test_agent_tools.py` (patch `agent_workbench.adapters.config.app_data_dir` → `tmp_path`;
  configs from `tests/adapters/tool_fixtures.py` with the temp `database_config`):
  - **agent loop**: real `Toolsets` → `build_tools` → `build_graph` with a scripted model:
    call 1 → tool calls `read_tables(schema="main")` and
    `save_file(file_path="report.md", content="# Report")`; call 2 → "done". Run via
    `run_turn` with recording `on_tool_start` / `on_tool_end`. Assert: `customers` in the
    `read_tables` result, `report.md` written in the workspace, two lines in
    `tmp_path/logs/tool_calls.jsonl` with `outcome == "ok"`, both callbacks fired twice.
    The Chainlit tool step part of this acceptance criterion is covered in step 10
    (real `run_turn` with real tools feeding `ToolSteps`).
  - **only hard-coded tools bound**: `get_runtime` with `config_file.tools` set
    (write `tmp_path/config.toml`), `load_llm_config` / `create_chat_model` patched,
    `bind_tools` spied → bound names == `{read_schemas, read_tables, read_columns,
    read_relations, validate_sql, read_file, list_directory, search_files, save_file,
    edit_file, append_file}`; `verify`, `count_records`, `delete_this_file` absent.
  - duplicate tool names fail `get_runtime` (patch `tool_specs` as in step 6) and the
    checkpointer is not left open.
  - `close_runtime` closes the SQL toolset; and still closes it when
    `checkpointer.conn.close` raises (the error propagates).
  - no `[tools]` → `Runtime.toolsets is None`, graph built with no tools.
  - non-table `[tools]` (`tools = "x"` in `tmp_path/config.toml`) → `get_runtime` raises
    `ValueError` and the checkpointer is not left open.
- `tests/test_tool_path_no_mcp.py` (top level: it spans adapters and services): a script
  run with `sys.executable` in a subprocess
  (`subprocess.run([...], capture_output=True, text=True, timeout=120, check=False)  # noqa: S603`;
  `env={**os.environ, "PYTHONPATH": "src"}` – not a fresh dict: Windows needs
  `SYSTEMROOT` and the rest of the environment) that imports only `agent_workbench.adapters.config`,
  `agent_workbench.adapters.tools`, `agent_workbench.services.tool_call_log`,
  `agent_workbench.services.tool_filter` and both tool packages – never
  `agent_workbench.apps` – points `config.app_data_dir` at the temp folder, builds the
  toolsets from temp configs, wraps and adapts them, `asyncio.run`s `read_tables` and
  `list_directory` through `tool.ainvoke`, and prints whether any `mcp` / `mcp.*` module
  is in `sys.modules`. Assert return code 0 and output `False`.

## DATA
`Runtime.toolsets: Toolsets | None`; `build_tools` → `list[StructuredTool]`.
