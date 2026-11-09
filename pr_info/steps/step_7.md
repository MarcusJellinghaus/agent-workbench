# Step 7 – Logging setup in `services`

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 7
only, test first: a `services` function that sets up logging through `mcp_coder_utils` and applies
mcp_coder's LLM-related third-party suppression. Make all checks pass and produce exactly one commit.

## WHERE
- New `src/agent_workbench/services/logging_setup.py`
- New `tests/services/__init__.py` (empty), `tests/services/test_logging_setup.py`
- Modified `.importlinter` (`mcp_coder_utils_isolation`: allow services)

## WHAT
```python
LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "OUTPUT", "WARNING", "ERROR", "CRITICAL")  # as mcp_coder's --log-level

def setup_logging(log_level: str) -> None:
    """Configure logging (mcp_coder_utils) and quieten SDK request logs."""
```

## HOW
- `from mcp_coder_utils.log_utils import setup_logging as _upstream_setup_logging`
  (same alias as mcp_coder's `utils/log_utils.py`, so tests patch
  `agent_workbench.services.logging_setup._upstream_setup_logging`).
- `LOG_LEVELS` lives here so `interfaces` (which may not import `mcp_coder_utils`) can use it for argparse
  `choices` without duplicating the list.
- `.importlinter`, contract `mcp_coder_utils_isolation`: add
  `agent_workbench.services.** -> mcp_coder_utils` to `ignore_imports`.

## ALGORITHM
```
_upstream_setup_logging(log_level)
for name in ("openai._base_client", "urllib3.connectionpool"): logging.getLogger(name).setLevel(logging.INFO)
for name in ("httpcore", "httpx"): logging.getLogger(name).setLevel(logging.WARNING)
```
(The `github.*` entries of mcp_coder are not needed.)

## DATA
None.

## Tests (write first)
- `_upstream_setup_logging` (patched) called with the level;
- after the call, the four loggers have the expected levels (restore their previous levels in a
  fixture so other tests are unaffected).

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports. One commit:
`Add logging setup with SDK log suppression`.
