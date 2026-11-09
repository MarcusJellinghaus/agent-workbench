# Step 1 – `core.types`: copy `TokenUsage` and `format_token_count`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 1: copy iCoder's
`TokenUsage` and `format_token_count` into `agent_workbench.core.types`, with the matching
mcp_coder tests. Tests first, then code; all checks pass; one commit.

## WHERE
- Create `src/agent_workbench/core/types.py`
- Create `tests/core/test_types.py`

## WHAT
Copy verbatim from mcp_coder `033a9d05:src/mcp_coder/icoder/core/types.py` only:
```python
def format_token_count(n: int) -> str: ...

@dataclass
class TokenUsage:
    last_input: int = 0
    last_output: int = 0
    total_input: int = 0
    total_output: int = 0
    last_cache_read: int = 0
    total_cache_read: int = 0
    _ever_updated: bool = field(default=False, repr=False)
    def update(self, input_tokens: int, output_tokens: int, cache_read_input_tokens: int = 0) -> None: ...
    def display_text(self) -> str: ...
    @property
    def has_data(self) -> bool: ...
```
Imports: only `dataclasses` (`dataclass`, `field`) and `from __future__ import annotations`.
Nothing else from the source file.

## HOW
- First line of both files: `# Copied from mcp_coder <source path> at commit 033a9d05.`
  followed by a note that only `format_token_count` / `TokenUsage` (and their tests) were copied.
- Module docstring: "Token usage types copied from mcp_coder's iCoder."
- Tests: copy from `033a9d05:tests/icoder/test_types.py` the tests for
  `format_token_count` and `TokenUsage` (from `test_format_token_count_zero` through the
  last `TokenUsage` test); change the import to `agent_workbench.core.types`.
- `core` imports nothing outside the standard library – import-linter `core_independence`
  stays green.

## ALGORITHM
None (verbatim copy).

## DATA
`TokenUsage.display_text()` → e.g. `"↓1.2k ↑340 | total: ↓5.0k ↑1.1k"` (cache share appended when > 0).

## Checks / commit
pylint, pytest, mypy, ruff, vulture (add a whitelist entry only for names vulture still
reports, comment `core/types.py: …`). Commit: `feat(core): copy TokenUsage from mcp_coder iCoder`.
