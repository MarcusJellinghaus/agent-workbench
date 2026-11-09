# Step 6 – `verify` checks and exit code in `services/verify.py`

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 6
only, test first: the `verify` checks as a structured report (no printing), callable without argparse.
Follow the LLM part of mcp_coder's `cli/commands/verify.py`, `verify_exit_code.py` and
`utils/user_config.verify_config` at `f88e6b55`. Make all checks pass and produce exactly one commit.

## WHERE
- New `src/agent_workbench/services/verify.py`
- New `tests/services/test_verify.py`

## WHAT
```python
TEST_PROMPT = "Reply with OK"
TEST_PROMPT_TIMEOUT = 30

@dataclass
class VerifyReport:
    config_path: Path
    config_entries: list[dict[str, str]]   # {"label", "status": "ok"|"warning"|"error"|"info", "value"}
    config_has_error: bool
    backend: str | None                    # LLM PROVIDER section
    provider: dict[str, Any]               # check_provider() rows incl. "effective_config" and "overall_ok"
    test_prompt_error: str | None          # None = responded OK; else the category text
    install_hints: list[str]
    exit_code: int

def verify_config(config_file: ConfigFile) -> tuple[list[dict[str, str]], bool]: ...
def collect_install_hints(rows: dict[str, Any]) -> list[str]: ...
def compute_exit_code(config_has_error: bool, overall_ok: bool, test_prompt_ok: bool) -> int: ...
def run_verify(check_models: bool = False) -> VerifyReport: ...
```

## HOW
- Module level imports: stdlib, `agent_workbench.adapters.config` (module), `agent_workbench.adapters.llm`
  (module), `agent_workbench.adapters.config_hints.unknown_key_hint`, `agent_workbench.core.config.LLM_KEYS`.
  None of these imports `adapters.langchain` at module level.
- Inside `run_verify`: `from agent_workbench.adapters.langchain import _provider_checks` and
  `from agent_workbench.adapters.langchain._exceptions import classify_connection_error, format_diagnostics`;
  call `_provider_checks.check_provider(...)` through the module so tests can patch
  `agent_workbench.adapters.langchain._provider_checks._check_package_installed`.
- Chat model and call via `llm.create_chat_model` / `llm.invoke` (patchable at
  `agent_workbench.adapters.llm.*`).
- `logger = logging.getLogger(__name__)`; failure details at DEBUG (`exc_info=True`), as mcp_coder.

## ALGORITHM
```
verify_config(cf):                                   # mirrors mcp_coder verify_config for the [llm] section
    missing  -> [Config file|warning|not found], [Expected path|info|<path>],
                [Hint|info|See the Configuration section of the README to create it]; has_error False
    parse_error -> [Config file|error|invalid TOML], [Parse error|error|<parse_error>]; return (entries, True)
    ok       -> [Config file|ok|<path>]
    per key in LLM_KEYS (label "[llm]"): env var set -> ok "<key> configured (env var)";
        wrong type -> error "<key>: expected str, got <type> ('<value>')"; in file -> ok "<key> configured (config.toml)";
        else info "<key> not configured"   (no [llm] table and no env var at all -> single info "not configured")
    unknown keys -> warning "unknown key: <key>" + (" — " + hint) from unknown_key_hint("llm", key, LLM_KEYS)

run_verify(check_models):
    cf = adapters.config.read_config_file(); entries, has_err = verify_config(cf)
    config = adapters.config.load_llm_config(cf)
    rows = _provider_checks.check_provider(config.as_dict(), check_models=check_models)
    try: llm.invoke(llm.create_chat_model(config, TEST_PROMPT_TIMEOUT), config, TEST_PROMPT); error = None
    except Exception as exc: error = classify_connection_error(exc) if isinstance(exc, (OSError, ConnectionError))
                                     else f"{type(exc).__name__}: {exc}"   (+ debug log of format_diagnostics)
    hints = collect_install_hints(rows); exit = compute_exit_code(has_err, bool(rows["overall_ok"]), error is None)
```
`collect_install_hints`: `install_hint` of every dict entry whose `ok` is falsy (as mcp_coder's
`_collect_install_hints`). `compute_exit_code`: `1` if config error, `not overall_ok` or failed test prompt,
else `0`. `available_models` / `model_check` are never consulted – they stay outside `overall_ok`
(`check_provider` already keeps them out), so `--check-models` cannot change the exit code.

## DATA
`VerifyReport` as above. For a missing provider package `install_hints == ["pip install langchain-openai"]`
(raw package, as mcp_coder). A runtime `ImportError` from a backend ends in `test_prompt_error` and names
`agent-workbench[langchain]` (from `_product.INSTALL_HINT`).

## Tests (write first, `tests/services/test_verify.py`)
Fixture: `monkeypatch.delenv` the `AGENT_WORKBENCH_LLM_*` and vendor key vars (`OPENAI_API_KEY`, …,
`OPENAI_BASE_URL`, `OLLAMA_HOST`), patch `agent_workbench.adapters.config.config_file_path` to a
`tmp_path` file. Patch `agent_workbench.adapters.llm.create_chat_model` to return a `MagicMock`
(never the real backends, so no `langchain_core` is needed):
- CONFIG rows – one test each, asserting `config_entries` / `config_has_error`: file ok, env-var source,
  empty env var, missing file (warning + expected path + README hint), invalid TOML (error + Parse error row),
  wrong type (error), unknown key (warning with "did you mean" hint, e.g. `modle`);
- happy path: `backend = "openai"`, fake model answering → `test_prompt_error is None`, `exit_code` 0
  when `_check_package_installed` is patched to `True`;
- package missing: `_provider_checks._check_package_installed` patched to `False` → install hint
  `pip install langchain-openai`, `exit_code` 1;
- unreachable provider: fake model `invoke` raises `ConnectionError` → `test_prompt_error` set, `exit_code` 1;
- runtime import error: `create_chat_model` raises `ImportError(INSTALL_HINT)` → error text names
  `agent-workbench[langchain]`;
- `check_models=True` with failing listing (`_provider_checks._list_models_for_backend` patched to
  `{"ok": False, "value": [], "error": "x"}`) and an otherwise passing run → `exit_code` 0;
- ollama without tool calling (`_models.check_ollama_tool_capability` / `_models._check_ollama_daemon`
  patched in `agent_workbench.adapters.langchain._models`) → `overall_ok` False → `exit_code` 1;
- config error alone → `exit_code` 1; `compute_exit_code` truth table.

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports, tach. One commit:
`Add verify checks for config and LLM provider`.
