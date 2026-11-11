# Step 10 – Runtime wiring, tool filter, logger clamp, agent-loop and `mcp` tests

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_10.md`), then implement
this step only. Reference for the subprocess test: mcp-tools-sql
`tests/test_module_imports.py::test_toolset_does_not_import_mcp`. TDD: tests first. Run
pylint, pytest (`-n auto -m "not integration"`), mypy, lint-imports and tach; all must
pass. One commit.

## WHERE
- new `src/agent_workbench/services/tool_filter.py`
- `src/agent_workbench/services/logging_setup.py` (`clamp_loggers`)
- `src/agent_workbench/apps/agent.py` (`Runtime`, `build_tools`, `get_runtime`, `close_runtime`)
- new `tests/services/test_tool_filter.py`
- `tests/services/test_logging_setup.py`
- new `tests/apps/test_agent_tools.py`
- new `tests/test_tool_path_no_mcp.py` (`integration`)
- `tests/apps/test_agent_graph.py` / `test_agent_checkpointer.py` (runtime tests, if needed)

## WHAT
```python
# services/tool_filter.py
ENABLED_GROUPS: frozenset[str] = frozenset({"sql.schema", "workspace.read", "workspace.write"})
ENABLED_TOOLS: frozenset[str] = frozenset({"validate_sql"})  # its group also holds `verify`

def enabled_specs(specs: Iterable["ToolSpec"]) -> tuple["ToolSpec", ...]:
    """Return the specs offered to the model until #18's permission resolver replaces this."""

# services/logging_setup.py
def clamp_loggers(names: Iterable[str]) -> None:
    """Set each named logger to ``INFO``: tool packages log parameters and results at DEBUG."""

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
  `llm_config = load_llm_config(config_file)`; when `config_file.tools or
  config_file.tools_type_error`: `clamp_loggers(provider_packages(config_file.tools))`
  (registered names only; unknown names fail in the build), then
  `toolsets = build_toolsets(config_file)` (a non-table `[tools]` reaches
  `build_toolsets` and raises – no silent run without tools); otherwise `None`. Then the
  checkpointer and the graph with `build_tools(toolsets) if toolsets else []`. Close what
  was opened if a later step fails.
- `close_runtime`: close the checkpointer connection in `try`, the toolsets in `finally`.

## ALGORITHM
```
toolsets = saver = None
try:
    if config_file.tools or config_file.tools_type_error:
        clamp_loggers(provider_packages(config_file.tools))
        toolsets = build_toolsets(config_file)
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
  only schema, `validate_sql`, read and write remain, order kept (specs built with
  `tool_spec` over small functions; no tool package).
- `test_logging_setup.py`: `clamp_loggers(["pkg_a", "pkg_b"])` after `setup_logging("DEBUG")`
  → both at `INFO`.
- `test_agent_tools.py` (patch `agent_workbench.adapters.config.app_data_dir` → `tmp_path`;
  fake providers via `tests/adapters/tool_fixtures.py`):
  - **agent loop**: a fake provider with one sync and one async tool → `build_toolsets` →
    `build_tools` → `build_graph` with a scripted model: call 1 → both tool calls; call 2 →
    "done". Run via `run_turn` with recording `on_tool_start` / `on_tool_end`. Assert: both
    results returned to the model, two lines in `tmp_path/logs/tool_calls.jsonl` with
    `outcome == "ok"`, both callbacks fired twice. The Chainlit tool step part is covered
    in step 11.
  - **only hard-coded tools bound**: `get_runtime` with a `[tools.fake]` table whose fake
    tools carry the groups / names of the filter test (write `tmp_path/config.toml`,
    `load_llm_config` / `create_chat_model` patched, `bind_tools` spied) → bound names are
    exactly the schema, `validate_sql`, read and write tools; `verify`, profiling and delete
    tools absent.
  - `get_runtime` calls `clamp_loggers` with the fake provider's package.
  - duplicate tool names across two fake providers fail `get_runtime` and the checkpointer
    is not left open.
  - `close_runtime` closes the toolsets; and still closes them when
    `checkpointer.conn.close` raises (the error propagates).
  - no `[tools]` → `Runtime.toolsets is None`, graph built with no tools, no provider loaded.
  - non-table `[tools]` (`tools = "x"` in `tmp_path/config.toml`) → `get_runtime` raises
    `ValueError` and the checkpointer is not left open.
  - **integration** (`@pytest.mark.integration`, skip unless `sql` and `workspace` are in
    `registered_providers()`): the same agent loop with the real providers on a temp SQLite
    database (temp `database_config`, so `~/.mcp-tools-sql/config.toml` is never read) and
    a temp workspace: `read_tables(schema="main")` returns `customers`,
    `save_file(file_path="report.md", content="# Report")` writes the file.
- `tests/test_tool_path_no_mcp.py` (top level: it spans adapters and services;
  `@pytest.mark.integration`, same skip): a script run with `sys.executable` in a
  subprocess (`subprocess.run([...], capture_output=True, text=True, timeout=120,
  check=False)  # noqa: S603`; `env={**os.environ, "PYTHONPATH": "src"}` – not a fresh
  dict: Windows needs `SYSTEMROOT` and the rest of the environment) that imports only
  `agent_workbench.adapters.config`, `agent_workbench.adapters.tools`,
  `agent_workbench.services.tool_call_log` and `agent_workbench.services.tool_filter` –
  never `agent_workbench.apps` – points `config.app_data_dir` at the temp folder, builds
  the real providers' toolsets from temp configs through `build_toolsets`, wraps and adapts
  them, `asyncio.run`s `read_tables` and `list_directory` through `tool.ainvoke`, and prints
  whether any `mcp` / `mcp.*` module is in `sys.modules`. Assert return code 0 and output
  `False`. The per-package guarantee lives in the providers' own tests.

## DATA
`Runtime.toolsets: Toolsets | None`; `build_tools` → `list[StructuredTool]`.
