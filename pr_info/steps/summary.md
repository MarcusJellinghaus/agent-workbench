# Summary – #14 LLM core: copy the LangChain model layer, config and `verify`

Step 2 of epic #12. agent-workbench gets a working LLM path before any UI exists:
the LangChain model layer copied from mcp_coder, its own config, provider extras,
`agent-workbench verify` and a one-shot `agent-workbench prompt`.

Source of every copy: mcp_coder commit `f88e6b55` (MarcusJellinghaus/mcp_coder PR #1400).
Read each source / test file with
`mcp__mcp-workspace__git(command="show", args=["f88e6b55:<path>"], reference_name="mcp_coder", compact=False, max_lines=<large enough>)`.
Never use `read_reference_file` / `search_reference_files` for the copy (working tree may differ).

## Architectural / design changes

| Layer | Before | After |
|---|---|---|
| core | `greeting.py` placeholder | `config.py`: `LLM_KEYS`, frozen dataclass `LLMConfig` (five optional `str` fields, `as_dict()`) |
| adapters | empty | copied model layer `adapters/langchain/` (15 modules, empty `__init__`), flat copies `llm_types`, `config_hints`, `ssl_setup`, `toml_utils`; own `config.py` (file reader + loader) and `llm.py` (public chat-model / error-mapping / invoke functions) |
| services | empty | `logging_setup.py` (mcp_coder_utils logging + LLM third-party suppression), `verify.py` (all checks, structured `VerifyReport`, exit code – no printing) |
| interfaces | `--name` greeting CLI | argparse CLI with `--version`, `--log-level`, `verify [--check-models]`, `prompt <text> [--timeout]`; `verify_formatting.py` prints the report |

Design decisions (KISS):
- **Copies stay unchanged.** Only absolute import paths change (`mcp_coder.llm.types` → `..llm_types`,
  `mcp_coder.utils.config_hints` → `..config_hints`, `mcp_coder.utils.log_utils.token_fingerprint` →
  `mcp_coder_utils.redaction`), plus a header comment and the `_product.py` values. Relative imports untouched.
- **One config reader.** `adapters.config.read_config_file()` returns a `ConfigFile` (path, exists,
  parse error, raw `[llm]` table). `load_llm_config()` and `services.verify`'s CONFIG section both use it,
  so the loader and `verify` never disagree about a cause.
- **Config precedence** as mcp_coder: `AGENT_WORKBENCH_LLM_{BACKEND,MODEL,BASE_URL,API_VERSION}`
  (empty = unset) → `~/.agent_workbench/config.toml` `[llm]` → unset. No app env var for `api_key`
  (the copied backends let the vendor env var win). Missing file: env vars still apply.
  Invalid TOML or a wrong-typed value: every key unset, warning logged (as mcp_coder's loader).
- **Public adapters surface for #15** (`adapters/llm.py`): `create_chat_model`, `map_provider_error`,
  `invoke`. `apps` never imports private names of the copies.
- **`verify` = data first, print later.** `services.verify.run_verify()` returns a `VerifyReport`;
  `interfaces` prints it in mcp_coder's section order. Exit code only from CONFIG errors,
  `overall_ok` and the test prompt – never from row symbols; `--check-models` rows are advisory.
- **Light `--version`.** No module the CLI imports at top level imports `adapters.langchain` at
  module level; `adapters.llm` and `services.verify` import the copies inside function bodies;
  the CLI imports adapters / `services.verify` inside the handlers.
- **Small formatter.** Only mcp_coder's LangChain subset of `verify_formatting`
  (`pad`, `format_row`, `format_section`, label map, CONFIG grouping).
- **Layering contracts.** import-linter: model-layer self-containment, ancestor contract
  (`as_packages = False`), one `forbidden` contract per third-party module.

## Files created / modified

```
pyproject.toml                                    modified (deps, extras, mypy, deptry, import-linter floor)
.importlinter                                     modified (model-layer + third-party contracts)
vulture_whitelist.py                              modified
.large-files-allowlist                            modified only if a copied file exceeds 750 lines
.claude/CLAUDE.md                                 modified (pytest note)
pr_info/pr_notes.md                               new only if needed (skipped copied tests, dropped import-linter entries – for the PR description)
README.md                                         modified
docs/architecture/architecture.md                 modified

src/agent_workbench/core/greeting.py              deleted
src/agent_workbench/core/config.py                new
src/agent_workbench/adapters/llm_types.py         new (copy of llm/types.py)
src/agent_workbench/adapters/config_hints.py      new (copy of utils/config_hints.py)
src/agent_workbench/adapters/ssl_setup.py         new (copy of utils/ssl_setup.py)
src/agent_workbench/adapters/toml_utils.py        new (copy of utils/toml_utils.py)
src/agent_workbench/adapters/langchain/__init__.py   new (docstring only)
src/agent_workbench/adapters/langchain/{anthropic_backend,gemini_backend,ollama_backend,openai_backend,
    _models,_setup,_http,_exceptions,_errors_404,_usage,_preflight,_config_diagnostics,_messages,
    _provider_checks,_product}.py                 new (copies)
src/agent_workbench/adapters/config.py            new
src/agent_workbench/adapters/llm.py               new
src/agent_workbench/services/logging_setup.py     new
src/agent_workbench/services/verify.py            new
src/agent_workbench/interfaces/verify_formatting.py  new
src/agent_workbench/interfaces/cli.py             rewritten

tests/core/test_greeting.py                       deleted
tests/core/test_config.py                         new
tests/adapters/__init__.py                        new
tests/adapters/test_config_hints.py               new (copy)
tests/adapters/test_ssl_setup.py                  new (copy)
tests/adapters/test_toml_utils.py                 new (TestFormatTomlError copy)
tests/adapters/test_config.py                     new
tests/adapters/test_llm.py                        new
tests/adapters/langchain/__init__.py              new
tests/adapters/langchain/conftest.py              new (trimmed copy)
tests/adapters/langchain/test_langchain_{anthropic,contract,diagnostics,exceptions,gemini,http,messages,
    models,models_ollama,ollama,openai,provider_checks,resolve_target}.py   new (copies)
tests/services/__init__.py                        new
tests/services/test_logging_setup.py              new
tests/services/test_verify.py                     new
tests/interfaces/test_cli.py                      rewritten
tests/interfaces/test_verify_formatting.py        new
tests/interfaces/test_prompt_integration.py       new (marker `integration`)
```

## Steps

1. Flat copies `llm_types`, `config_hints`, `ssl_setup`, `toml_utils` + their copied tests.
2. Copied LangChain model layer + copied tests + packaging + import-linter contracts.
3. Config: `core.config.LLMConfig` + `adapters.config` reader / loader.
4. Public LLM functions `adapters.llm`.
5. Logging setup `services.logging_setup`.
6. `services.verify` checks and exit code.
7. CLI: `verify` / `prompt` subcommands, formatter, placeholder removal, integration test.
8. Docs (README, architecture.md, CLAUDE.md pytest note) and final checks.

## Rules for every step
- Checks after the change: `run_pylint_check`, `run_pytest_check(extra_args=["-n", "auto", "-m", "not integration"])`,
  `run_mypy_check`, `run_ruff_check`, `run_lint_imports_check`; `run_format_code` before the commit.
- If a check fails because a package declared in `pyproject.toml` is not installed in the active
  environment (e.g. `ModuleNotFoundError: langchain_core` not covered by the conftest fakes, or mypy
  cannot find it), write one line to `pr_info/.blocked.txt` naming the package and stop.
- Tests outside `tests/adapters/langchain/` must not need `langchain_core` (installed or faked): patch
  `agent_workbench.adapters.langchain._setup._create_chat_model` or the backends instead.
- Every patch target names the module where the patched name is looked up.
- Copied file header (first line, before the docstring):
  `# Copied from mcp_coder <source path> at commit f88e6b55 (MarcusJellinghaus/mcp_coder#1400).`
- Before committing a copy, compare it with its `git show` output: only the header, the allowed import
  rewrites, the import-order re-sort and (for `_product.py` / listed test literals) the allowed changes differ.
