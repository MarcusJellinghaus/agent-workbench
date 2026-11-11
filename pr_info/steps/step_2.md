# Step 2 – `mcp_coder_utils` shims and tightened import contract

## LLM prompt
Read `pr_info/steps/summary.md` (section "Logging strategy") and this file
(`pr_info/steps/step_2.md`), then implement this step only. Pattern: mcp_coder's
`src/mcp_coder/utils/user_app_data.py` and its `.importlinter` contract
`mcp_coder_utils_isolation` (reference project `mcp_coder`). TDD: tests first. Run pylint,
pytest (`-n auto -m "not integration"`), mypy and lint-imports; all must pass. One commit.

## WHERE
- new `src/agent_workbench/adapters/redaction.py`
- new `src/agent_workbench/adapters/tool_spec.py`
- new `src/agent_workbench/adapters/user_app_data.py`
- `src/agent_workbench/adapters/config.py` (import only)
- `src/agent_workbench/adapters/langchain/_provider_checks.py` (import only)
- `.importlinter`
- new `tests/adapters/test_shims.py`

## WHAT
Each shim is a re-export with a one-line docstring and `__all__`:
```python
"""Redaction shim — re-exports from mcp_coder_utils."""
from mcp_coder_utils.redaction import REDACTED_VALUE, SENSITIVE_KEY_PATTERNS, token_fingerprint
__all__ = ["REDACTED_VALUE", "SENSITIVE_KEY_PATTERNS", "token_fingerprint"]
```
```python
"""Tool contract shim — re-exports from mcp_coder_utils.

Import only under TYPE_CHECKING or lazily on the tool path: the core
``mcp-coder-utils>=0.1.6`` floor has no ``tool_spec``.
"""
from mcp_coder_utils.tool_spec import ToolCollector, ToolSpec
__all__ = ["ToolCollector", "ToolSpec"]
```
```python
"""User app data directory shim — re-exports from mcp_coder_utils."""
from mcp_coder_utils.user_app_data import get_user_app_data_dir
__all__ = ["get_user_app_data_dir"]
```

## HOW
- `adapters/config.py`: `from agent_workbench.adapters.user_app_data import get_user_app_data_dir`.
- `_provider_checks.py`: `from agent_workbench.adapters.redaction import token_fingerprint`.
- `.importlinter`:
  - `mcp_coder_utils_isolation`: rename to `mcp_coder_utils only through the shims`, comment
    "only the four shim modules import mcp_coder_utils; everything else uses them", and
    replace both `ignore_imports` lines with exactly:
    ```
    agent_workbench.adapters.redaction -> mcp_coder_utils
    agent_workbench.adapters.tool_spec -> mcp_coder_utils
    agent_workbench.adapters.user_app_data -> mcp_coder_utils
    agent_workbench.services.logging_setup -> mcp_coder_utils
    ```
  - `langchain_model_layer`: add
    `agent_workbench.adapters.langchain._provider_checks -> agent_workbench.adapters.redaction`.
- `tach.toml`: no change.

## Tests (`tests/adapters/test_shims.py`)
- Each shim exports the same objects as its `mcp_coder_utils` source
  (`redaction.token_fingerprint is mcp_coder_utils.redaction.token_fingerprint`, etc.) –
  one parametrized test over `(shim module, source module, names)`.

## DATA
n/a
