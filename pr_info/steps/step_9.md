# Step 9 – CLI: `verify` and `prompt` subcommands, formatter, placeholder removal

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 9
only, test first: rewrite the CLI with `--log-level`, `verify` and `prompt`, add the verify formatter,
remove the greeting placeholder, add the real-provider integration test. Make all checks pass and
produce exactly one commit.

## WHERE
- Rewritten `src/agent_workbench/interfaces/cli.py`
- New `src/agent_workbench/interfaces/verify_formatting.py`
- Deleted `src/agent_workbench/core/greeting.py`, `tests/core/test_greeting.py`
- Rewritten `tests/interfaces/test_cli.py`
- New `tests/interfaces/test_verify_formatting.py`, `tests/interfaces/test_prompt_integration.py`

## WHAT
`verify_formatting.py` (standard library + `agent_workbench.services.verify.VerifyReport` only) –
the LangChain subset of mcp_coder's `cli/commands/verify_formatting.py` and the printing in `verify.py`:
```python
STATUS_SYMBOLS = {"success": "[OK]", "failure": "[ERR]", "warning": "[WARN]"}
_LABEL_WIDTH = 22
def pad(title: str) -> str: ...                                   # "\n=== TITLE ====…" to 75 chars
def format_row(label: str, marker: str, value: str, *, indent: int) -> str: ...
def format_section(title: str, rows: dict[str, Any]) -> str: ...  # skips "overall_ok" and non-dict entries
def format_config_section(entries: list[dict[str, str]]) -> str: ...
def format_report(report: VerifyReport) -> str: ...
```
`_LABEL_MAP`: the LangChain entries of mcp_coder's map (`backend`, `model`, `api_key`, `api_version`,
`langchain_core`, `backend_package`, `base_url`, `base_url_shape`, `base_url_redirect`, `api_key_override`,
`available_models`, `model_check`, `ollama_daemon`, `ollama_tools_capability`). No MCP / GitHub / Git parts.

`cli.py`:
```python
def main(argv: list[str] | None = None) -> int: ...
def _build_parser() -> argparse.ArgumentParser: ...
def _run_verify(args: argparse.Namespace) -> int: ...
def _run_prompt(args: argparse.Namespace) -> int: ...
```
Arguments: `--version` (unchanged), `--log-level` (`type=str.upper`, `choices=LOG_LEVELS`, default
`"OUTPUT"`, `metavar="LEVEL"`), subcommand `verify` with `--check-models` (`store_true`), subcommand
`prompt` with positional `prompt` and `--timeout` (`int`, default 60).

## HOW
- `cli.py` top level imports: `argparse`, `logging`, `sys`, `importlib.metadata`,
  `agent_workbench.services.logging_setup` (`LOG_LEVELS`, `setup_logging`). Nothing else from
  adapters / services at top level – `verify` and `prompt` handlers import inside the function:
  `from agent_workbench.services.verify import run_verify`,
  `from agent_workbench.interfaces.verify_formatting import format_report`,
  `from agent_workbench.adapters import config as config_adapter, llm`.
- `main` order (as mcp_coder): UTF-8 reconfigure of stdout / stderr (`hasattr(..., "reconfigure")`),
  parse args, `setup_logging(args.log_level)`, then
  `from agent_workbench.adapters.ssl_setup import ensure_truststore; ensure_truststore()`, then dispatch.
  No subcommand → `parser.print_help()`, return 1.
- `interfaces` must not import `mcp_coder_utils`; errors are reported with stdlib
  `logging.getLogger(__name__).error(...)` (ERROR is shown at the default OUTPUT level).
- API keys only reach output through the copies' `_mask_api_key` / `token_fingerprint` (in the rows).

## ALGORITHM
```
_run_verify(args):  report = run_verify(check_models=args.check_models); print(format_report(report)); return report.exit_code

_run_prompt(args):
    try: config = config_adapter.load_llm_config(); model = llm.create_chat_model(config, args.timeout)
         print(llm.invoke(model, config, args.prompt)); return 0
    except Exception as exc: logger.error("Prompt command failed: %s", exc); return 1   # as mcp_coder

format_report(r):  CONFIG (config_path row + format_config_section)
                   -> LLM PROVIDER ("Active provider" row: backend or "not configured")
                   -> EFFECTIVE CONFIG (label/value pairs of r.provider["effective_config"], empty marker) if present
                   -> format_section("LLM PROVIDER DETAILS", r.provider)
                   -> "Test prompt" row: [OK] "responded OK" | [ERR] f"FAILED ({error})"
                      + "  Run with --log-level DEBUG for detailed diagnostics."
                   -> INSTALL INSTRUCTIONS "  pip install <pkgs>" from hints starting with "pip install"
```
`format_section` per row: symbol `[OK]` for `ok is True`, `[ERR]` for `False`, `[WARN]` otherwise;
append ` (<error>)` when `ok is False` and `error` is set; line `-> <install_hint>` under a failed row with
a hint (as mcp_coder). `format_config_section`: mcp_coder's loop – `[llm]` group header, rows split on the
first token when it `_looks_like_key`, status map ok→`[OK]`, warning→`[WARN]`, error→`[ERR]`, info→`""`.

## DATA
Exit codes: `verify` → `report.exit_code`; `prompt` → 0 / 1.

## Tests (write first)
`tests/interfaces/test_cli.py` – autouse fixture patches
`agent_workbench.interfaces.cli.setup_logging` and `agent_workbench.adapters.ssl_setup.ensure_truststore`:
- `--version` exits 0 and prints `agent-workbench `;
- no subcommand → 1;
- `verify` prints the report and returns `run_verify`'s exit code (patch
  `agent_workbench.services.verify.run_verify` with a fixed `VerifyReport`); `--check-models` forwarded;
- `--log-level debug` → `setup_logging("DEBUG")`;
- `prompt`, patching `agent_workbench.adapters.config.load_llm_config` (returns an openai `LLMConfig`) and
  `agent_workbench.adapters.langchain._setup._create_chat_model` (returns a fake model):
  answer printed / exit 0; 404 hint (`invoke` raises `Exception("404 not found")`, patch
  `_errors_404._get_model_suggestions`) → hint in `caplog`, exit 1; connection error (`ConnectionError`) and
  auth error (`LLMAuthError`) → exit 1 with message; missing key (real `_create_chat_model`, config without
  key, vendor env var deleted) → contract `ValueError` message, exit 1; other exception → exit 1;
  `--timeout 5` forwarded to `_create_chat_model`.
- light `--version`: parse with `ast` the modules the CLI imports at top level (`interfaces/cli.py`,
  `interfaces/__init__.py`, `services/__init__.py`, `services/logging_setup.py`, `adapters/__init__.py`,
  `core/__init__.py`) and assert no module-level import names `adapters.langchain`
  (a `sys.modules` check is unreliable under xdist).

`tests/interfaces/test_verify_formatting.py`: rows `[OK]` / `[ERR]` / `[WARN]` with labels;
`effective_config` list not rendered by `format_section`; install hint line; INSTALL INSTRUCTIONS joined;
test-prompt failure line mentions `--log-level DEBUG`; CONFIG grouping under `[llm]`.

`tests/interfaces/test_prompt_integration.py`: `pytestmark = pytest.mark.integration`; skip when
`load_llm_config().backend` is None, or the backend is not `ollama` and neither the config `api_key` nor
the vendor env var (`OPENAI_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`) is set; then
`main(["prompt", "Reply with OK"]) == 0` and a non-empty answer printed. Like every CLI test that calls
`main()`, it patches `agent_workbench.interfaces.cli.setup_logging` and
`agent_workbench.adapters.ssl_setup.ensure_truststore` (truststore injection is process-wide).

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports, tach, vulture. One commit:
`Add verify and prompt commands; remove greeting placeholder`.
