# Step 6 – Toolset building with lazy package imports

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`), then implement
this step only. Reference: mcp-tools-sql `src/mcp_tools_sql/toolset.py` and
`tests/test_toolset.py` (`_write_configs`), mcp-workspace `mcp_workspace.toolset.tool_specs`
(use `get_library_source`). TDD: tests first. Run pylint, pytest
(`-n auto -m "not integration"`), mypy, lint-imports, deptry (`run_deptry_check`) and
`tools/check_no_url_deps.py` (read it first for its invocation); all must pass. One
commit.

**Precondition:** `get_library_source("mcp_tools_sql.toolset.build_toolset")` and
`get_library_source("mcp_workspace.toolset.tool_specs")` both return source. If either is
not found, write one line to `pr_info/.blocked.txt` naming the missing module and stop.

## WHERE
- `src/agent_workbench/adapters/tools.py`
- `.importlinter`
- `pyproject.toml`
- new `tests/adapters/tool_fixtures.py`
- `tests/adapters/test_tools.py`

## WHAT
```python
@dataclass(frozen=True)
class Toolsets:
    """The tool specs of every configured package plus what must be closed."""

    specs: tuple["ToolSpec", ...]
    sql: Any = None  # mcp_tools_sql SqlToolset: owns the DB connections

    def close(self) -> None:
        """Close the SQL toolset's connections (no-op without one)."""

def build_toolsets(config_file: ConfigFile) -> Toolsets:
    """Build the tools of every package in ``[tools]``; close with ``Toolsets.close``.

    Raises:
        ValueError: A ``[tools]`` error (see ``tools_config_problems``) or a duplicate
            tool name across packages.
        ImportError: A configured package is not installed.
    """
```

## HOW
- Package imports only inside `build_toolsets`, per configured table:
  `from mcp_tools_sql.toolset import build_toolset`,
  `from mcp_workspace.toolset import tool_specs`; `ToolCollector` lazily from
  `agent_workbench.adapters.tool_spec`.
- `.importlinter`: two `forbidden` contracts in the style of `httpx_isolation`:
  `mcp_tools_sql only in adapters`, `mcp_workspace only in adapters`
  (`ignore_imports = agent_workbench.adapters.** -> <pkg>`).
- `pyproject.toml` (in this step, not earlier: before the first `src` import deptry
  reports the extras as unused, DEP002):
  1. New extras in `[project.optional-dependencies]` (after the LangChain extras, with a
     `# Tool packages (#17), imported only when configured` comment):
     ```toml
     sql = ["mcp-tools-sql"]
     sql-mssql = ["mcp-tools-sql[mssql]"]
     workspace = ["mcp-workspace"]
     ```
     No version floors – #20 adds them once the siblings are released.
  2. `dev`: `"agent-workbench[typecheck,coverage,langchain,sql,workspace]"`. Keep the
     `mcp-workspace` line (Claude Code MCP server) and its comment. Update the deptry
     comment: it names the self-referenced extras deptry does not expand.
  3. `[tool.mcp-coder.install-from-github] packages` gains
     `"mcp-tools-sql @ git+https://github.com/MarcusJellinghaus/mcp-tools-sql.git"`
     (with deps, next to `mcp-workspace`). No URL in `[project]` dependencies
     (`tools/check_no_url_deps.py`).

## ALGORITHM
```
errors = [m for label, status, m in tools_config_problems(config_file) if status == "error"]
if errors: raise ValueError("Invalid [tools] config: " + "; ".join(errors))
tools = config_file.tools; collector = ToolCollector(); sql = None
try:
    if "sql" in tools: sql = build_toolset(tool_path(qc), tool_path(db) if db else None); add sql.specs
    if "workspace" in tools: add tool_specs(tool_path(project_dir))
except BaseException: if sql: sql.close(); raise
return Toolsets(collector.specs, sql)
```
Each package uses its own `ToolCollector`; adding both packages' specs to one collector
makes a duplicate name raise `ValueError`.

## Tests
`tests/adapters/tool_fixtures.py` (plain helpers, no fixtures):
- `write_sql_configs(tmp_path) -> tuple[Path, Path]`: SQLite db with a `customers` table,
  query config `connection = "default"`, database config `[connections.default] backend =
  "sqlite"`, `path = "<db>"` (copy of mcp-tools-sql's `_write_configs`, no queries/updates).
  Tests always pass this temp `database_config`, so `~/.mcp-tools-sql/config.toml` is never
  read.
- `write_config_file(tmp_path, sql=True, workspace=True) -> Path`: an agent-workbench
  `config.toml` with absolute `[tools.sql]` / `[tools.workspace]` paths (workspace =
  `tmp_path / "ws"`, created).
- Read with `read_config_file(path)`.

`test_tools.py`:
- both packages configured → specs contain `read_tables` and `read_file`; `sql` set;
  `close()` closes it (spy on `sql.close` or `BackendRegistry.close_all`).
- workspace only, with `monkeypatch.setitem(sys.modules, "mcp_tools_sql.toolset", None)`
  → build succeeds (SQL package not imported when not configured).
- SQL configured, `mcp_tools_sql.toolset` blocked the same way → `ImportError`.
- duplicate name: patch `mcp_workspace.toolset.tool_specs` to return a spec named
  `read_tables` → `ValueError`, and the SQL toolset was closed.
- `[tools]` error (relative path) → `ValueError`, nothing built.

## DATA
`Toolsets(specs=tuple[ToolSpec, ...], sql=SqlToolset | None)`.
