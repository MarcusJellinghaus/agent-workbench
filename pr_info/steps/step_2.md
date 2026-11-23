# Step 2 – Move `Toolsets` / `build_toolsets` to `adapters/toolset_providers.py`

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`), and issue #18
(Scope "`verify`", the bullet on `services.verify` and `langchain_core`). Implement step 2
only: a pure move plus one import-linter contract, no behaviour change. Use
`mcp__mcp-tools-py__move_symbol` for the move, then fix what it leaves. Run pylint, pytest
(`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and lint-imports until all
pass. One commit.

## WHERE
- `src/agent_workbench/adapters/tools.py` (source)
- `src/agent_workbench/adapters/toolset_providers.py` (destination)
- Callers: `src/agent_workbench/apps/agent.py`, `src/agent_workbench/apps/tool_setup.py`
- Tests: `tests/adapters/test_tools.py`, `tests/adapters/test_toolset_providers.py`,
  `tests/apps/test_agent_tools.py`, `tests/apps/test_ui_handlers.py`,
  `tests/apps/test_ui_launcher.py` (patch targets), `tests/test_tool_path_no_mcp.py` (script text)
- `.importlinter`

## WHAT
Move unchanged: `class Toolsets` (with `close`) and `def build_toolsets(config_file: ConfigFile) -> Toolsets`.
`toolset_providers.py` then imports `ConfigFile`, `tools_config_problems` from
`adapters.config`, `dataclass`, `logging` (`logger = logging.getLogger(__name__)`), and keeps
the lazy `ToolCollector` import inside `build_toolsets` and the `TYPE_CHECKING` import of
`Toolset`, `ToolSpec`. `tools.py` keeps only `to_structured_tool`.

## HOW
- `toolset_providers.py` must stay free of `langchain_core` (it is today).
- `apps/tool_setup.py`: `toolset_providers.build_toolsets` / `toolset_providers.Toolsets`.
  Its module docstring still mentions the UI gate – leave it for step 3.
- `apps/agent.py`: import `Toolsets` from `toolset_providers`.
- Tests that move with the code: the `build_toolsets` / `Toolsets` tests go from
  `tests/adapters/test_tools.py` to `tests/adapters/test_toolset_providers.py` (the `caplog`
  logger name becomes `agent_workbench.adapters.toolset_providers`).
- Patch targets `agent_workbench.adapters.tools.build_toolsets` in `test_ui_launcher.py`
  become `agent_workbench.adapters.toolset_providers.build_toolsets` (these tests are
  rewritten in step 3; here they only follow the move).
- `tests/test_tool_path_no_mcp.py` `_SCRIPT`: import `build_toolsets` from
  `toolset_providers`, `to_structured_tool` from `tools`.
- Docstrings: `adapters/tools.py` module docstring (no toolsets any more);
  `adapters/toolset_providers.py` module docstring (discovery and toolset building).
- `.importlinter` – new contract:
```ini
# verify must work without the [langchain-base] extra: adapters.tools imports langchain_core
# at top level (langchain_core_isolation ignores adapters.** -> langchain_core).
[importlinter:contract:verify_without_langchain]
name = services.verify does not import adapters.tools
type = forbidden
source_modules =
    agent_workbench.services.verify
forbidden_modules =
    agent_workbench.adapters.tools
```

## DATA
Unchanged.

## Tests
Existing tests, moved and re-pointed; all pass unchanged in substance.
