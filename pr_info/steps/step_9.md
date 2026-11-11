# Step 9 – Toolset providers: entry-point discovery and `build_toolsets`

## LLM prompt
Read `pr_info/steps/summary.md`, `pr_info/steps/Decisions.md` and this file
(`pr_info/steps/step_9.md`), then implement this step only. Reference: mcp_coder
`src/mcp_coder/utils/toolkit_runner.py` (`ENTRY_POINT_GROUP`, `_toolkit_class`) and
`tests/utils/test_toolkit_runner.py` (patching `entry_points`); mcp-coder-utils
`mcp_coder_utils.tool_provider` (`ToolsetProvider`, `Toolset`, `StaticToolset`; use
`get_library_source`). TDD: tests first. Run pylint, pytest (`-n auto -m "not integration"`),
mypy, lint-imports, deptry (`run_deptry_check`) and `tools/check_no_url_deps.py` (read it
first for its invocation); all must pass. One commit.

**Precondition:** `get_library_source("mcp_coder_utils.tool_provider.ToolsetProvider")` returns
source (MarcusJellinghaus/mcp-coder-utils#61). If not found, write one line to
`pr_info/.blocked.txt` naming the missing module and stop. The tool packages
(`mcp_tools_sql`, `mcp_workspace`) are **not** needed: unit tests use a fake provider.

## WHERE
- `src/agent_workbench/adapters/tool_spec.py` (shim: re-export the provider contract)
- new `src/agent_workbench/adapters/toolset_providers.py` (discovery; no `langchain_core`)
- `src/agent_workbench/adapters/tools.py` (`Toolsets`, `build_toolsets`; module docstring)
- `.importlinter`
- `pyproject.toml`
- new `tests/adapters/tool_fixtures.py`
- new `tests/adapters/test_toolset_providers.py`, `tests/adapters/test_tools.py`,
  `tests/adapters/test_shims.py`

## WHAT
```python
# adapters/toolset_providers.py
ENTRY_POINT_GROUP = "agent_workbench.toolsets"

def registered_providers() -> list[str]:
    """Return the sorted names registered in the ``agent_workbench.toolsets`` group."""

def provider_class(name: str) -> type["ToolsetProvider"]:
    """Load the provider registered as *name*.

    Raises:
        ValueError: No entry point has the name (message lists the registered names and
            says to install the package that provides toolset '<name>'), or loading it fails.
    """

def provider_packages(names: Iterable[str]) -> list[str]:
    """Return the top-level package of each registered provider in *names*, without loading it."""

# adapters/tools.py
@dataclass(frozen=True)
class Toolsets:
    """The tool specs of every configured provider plus the toolsets to close."""

    specs: tuple["ToolSpec", ...]
    toolsets: tuple["Toolset", ...] = ()

    def close(self) -> None:
        """Close every toolset; a failing close is logged and the rest still close."""

def build_toolsets(config_file: ConfigFile) -> Toolsets:
    """Build the toolset of every ``[tools.<name>]`` provider; close with ``Toolsets.close``.

    Raises:
        ValueError: A ``[tools]`` shape error, an unregistered provider, a provider build
            error (``ValueError`` from ``build``) or a duplicate tool name across providers.
    """
```

## HOW
- Discovery uses `from importlib.metadata import entry_points` at module level (tests patch
  `toolset_providers.entry_points`); look up by name like `_toolkit_class`.
  `provider_packages`: `ep.value.split(":")[0].split(".")[0]`.
- `ToolsetProvider` / `Toolset` / `ToolSpec` / `ToolCollector`: from the
  `adapters.tool_spec` shim; in `src` only under `TYPE_CHECKING` or imported inside
  functions (core `mcp-coder-utils` floor has neither). Extend the shim to re-export
  `ToolsetProvider`, `Toolset`, `StaticToolset`.
- No module in `agent_workbench` imports a tool package. `.importlinter`: new `forbidden`
  contract `tool_packages_isolation` (source `agent_workbench`, forbidden `mcp_tools_sql`,
  `mcp_workspace`, no ignores). If lint-imports rejects a forbidden module that isn't
  installed, replace the contract with a test in `tests/adapters/test_toolset_providers.py`
  that parses every `src` module with `ast` and asserts neither package is imported, and
  note why in the test docstring.
- `pyproject.toml` (in this step):
  1. Extras in `[project.optional-dependencies]` after the LangChain extras, under a
     `# Toolset providers (#17) – install shortcuts; loaded by entry point, never imported`
     comment:
     ```toml
     sql = ["mcp-tools-sql"]
     sql-mssql = ["mcp-tools-sql[mssql]"]
     workspace = ["mcp-workspace"]
     ```
     No version floors – #20 adds them once the siblings are released.
  2. `[tool.deptry.per_rule_ignores] DEP002`: add `"mcp-tools-sql"`, `"mcp-workspace"` with
     a comment (plugins, loaded through entry points, never imported).
  3. `dev` and `[tool.mcp-coder.install-from-github]` unchanged (no tool package for tests;
     `mcp-workspace` stays in `dev` only as Claude Code's MCP server).

## ALGORITHM
```
errors = [m for _, status, m in tools_config_problems(config_file) if status == "error"]
if errors: raise ValueError("Invalid [tools] config: " + "; ".join(errors))
collector = ToolCollector(); built = []
try:
    for name, table in config_file.tools.items():
        toolset = provider_class(name)(table).build(); built.append(toolset)
        for spec in toolset.specs: collector.add(spec)       # duplicate name → ValueError
except BaseException:
    Toolsets((), tuple(built)).close(); raise
return Toolsets(collector.specs, tuple(built))
```

## Tests
`tests/adapters/tool_fixtures.py` (plain helpers, no fixtures):
- `FakeProvider(ToolsetProvider)`: `config["tools"]` = tool names (default `["echo"]`);
  `build()` returns a `FakeToolset` (specs from `tool_spec` over small sync / async
  functions, group from `config.get("group", "fake.read")`; `close()` records the call);
  `config.get("fail")` → `build` raises `ValueError`; `verify(connect=...)` returns rows from
  `config.get("rows", [])` and records `connect`.
- `register_providers(monkeypatch, providers: dict[str, type])`: patches
  `toolset_providers.entry_points` to return stub entry points (`name`, `value`
  `"<module>:<cls>"`, `load()` returning the class), as mcp_coder's toolkit runner tests do.
- `write_config_file(tmp_path, tables: dict[str, dict]) -> Path` writing `[tools.<name>]`
  tables; read with `read_config_file(path)`.

`test_toolset_providers.py`:
- `registered_providers` sorted; `provider_class` loads by name; unknown name →
  `ValueError` listing the registered names and the install hint; `load()` raising →
  `ValueError` naming the provider.
- `provider_packages(["a"])` → top-level package of the stub value, `load` not called.

`test_tools.py` (existing adapter tests stay):
- two fake providers → specs merged in config order; `toolsets` holds both.
- `close()` closes both; one `close` raising → logged, the other still closed.
- duplicate tool name across providers → `ValueError`, the first toolset closed.
- second provider's `build` raising → `ValueError`, the first toolset closed.
- unregistered `[tools.x]` → `ValueError` naming the registered providers.
- `[tools]` shape error → `ValueError`, no provider loaded.

`test_shims.py`: the shim re-exports `ToolsetProvider`, `Toolset`, `StaticToolset`.

## DATA
`Toolsets(specs=tuple[ToolSpec, ...], toolsets=tuple[Toolset, ...])`.
