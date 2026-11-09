# Step 2 – `adapters.llm.add_usage`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 2: a public
`add_usage` in `adapters/llm.py` wrapping the copied `_extract_usage` / `_sum_usage`, and
clean up the related vulture whitelist entries. Tests first, then code; all checks pass;
one commit.

## WHERE
- Modify `src/agent_workbench/adapters/llm.py`
- Modify `tests/adapters/test_llm.py`
- Modify `vulture_whitelist.py`

## WHAT
```python
def add_usage(total: UsageInfo, message: Any) -> UsageInfo:
    """Return *total* plus the usage carried by *message* (an AIMessage)."""
```

## HOW
- Import the copies inside the function body (module stays light, as the rest of `llm.py`):
  `from .langchain._usage import _extract_usage, _sum_usage`.
- `UsageInfo` from `agent_workbench.adapters.llm_types` (top-level import is fine – it has
  no third-party imports).
- `apps` will call only `llm.add_usage` – never the private names.

## ALGORITHM
```
usage = _extract_usage(message)
if not usage: return total
return _sum_usage(total, usage)
```

## DATA
`UsageInfo` dict; after the first message with usage it has all four keys
(`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`).

## Tests (`tests/adapters/test_llm.py`)
Use `types.SimpleNamespace(usage_metadata=...)` as message (no langchain needed):
- message without `usage_metadata` → `total` unchanged (`{}` stays `{}`).
- two messages summed field by field, incl. `input_token_details.cache_read`.

## Vulture whitelist
- Remove `_._extract_usage` and `_._sum_usage` (now used by `adapters.llm`).
- Update the comments of the remaining `(#15)` entries, which #15 does not use:
  `LLMMCPLaunchError` ("kept from mcp_coder; raised only by mcp_coder's MCP agent layer"),
  `assemble_messages` / `serialize_messages` ("used by the copied tests"),
  `_ollama_preflight` ("kept from mcp_coder; the startup `verify` covers Ollama tool
  calling"). Run vulture to confirm nothing else is reported.

## Checks / commit
pylint, pytest, mypy, ruff, vulture. Commit: `feat(adapters): add public add_usage helper`.
