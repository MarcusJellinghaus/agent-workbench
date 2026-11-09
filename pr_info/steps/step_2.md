# Step 2 – Copy the LangChain model layer (source modules only)

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 2
only: copy the 15 model-layer modules of mcp_coder (commit `f88e6b55`) into
`src/agent_workbench/adapters/langchain/`, add the packaging, mypy, deptry, import-linter and vulture
entries they need, make all checks pass, and produce exactly one commit. The copied tests follow in
Steps 3 and 4. This is a mechanical copy: do not refactor the copies.

## Precondition
If `git show f88e6b55:<path>` fails for a listed file, write one line to `pr_info/.blocked.txt` naming the
file and stop.

## WHERE
Source dir `src/mcp_coder/llm/providers/langchain/` → `src/agent_workbench/adapters/langchain/`:
`anthropic_backend`, `gemini_backend`, `ollama_backend`, `openai_backend`, `_models`, `_setup`, `_http`,
`_exceptions`, `_errors_404`, `_usage`, `_preflight`, `_config_diagnostics`, `_messages`,
`_provider_checks`, `_product` (`.py` each).
New `src/agent_workbench/adapters/langchain/__init__.py`: docstring only (no imports, no glue), e.g.
`"""LangChain model layer copied from mcp_coder (see each module's header)."""`.
Not copied: package `__init__` of mcp_coder, `_config_source`, `verification`, `agent`, `_mcp_tools`,
`mcp_manager`, `approval_bridge`, `permission_bridge`.

Modified: `pyproject.toml`, `.importlinter`, `vulture_whitelist.py`, `.large-files-allowlist` (only if needed).

## WHAT
Source copies – only these changes:
- header comment line;
- absolute imports: `from mcp_coder.llm.types import …` → `from agent_workbench.adapters.llm_types import …`
  (or the relative `..llm_types`, matching how the import is written – absolute stays absolute);
  `from mcp_coder.utils.config_hints import suggest` → `from agent_workbench.adapters.config_hints import suggest`;
  `from mcp_coder.utils.log_utils import token_fingerprint` → `from mcp_coder_utils.redaction import token_fingerprint`;
- `_product.py` values:
  ```python
  INSTALL_HINT = "Install with: pip install 'agent-workbench[langchain]'"
  OLLAMA_INSTALL_HINT = "Install with: pip install 'agent-workbench[langchain-ollama]'"
  CONFIG_SECTION = "[llm]"
  PRODUCT_NAME = "agent-workbench"
  ```
  Docstrings / comments keep mentioning mcp-coder.
- import-order re-sort by `run_format_code`.

## HOW
`pyproject.toml`: **already done** in separate commits before this step (done ahead of this step so the
environment could be reinstalled with the new packages). Structured as mcp_coder's: `dependencies` =
`truststore>=0.9.0`, `mcp-coder-utils>=0.1.6`; extra `langchain-base` (`langchain-core>=1.4.7`,
`httpx>=0.27.0`); provider extras `langchain-{openai,gemini,anthropic,ollama}` each pull
`agent-workbench[langchain-base]` + their wrapper; meta extra `langchain`; `dev` includes `langchain`;
`import-linter>=2.15`; mypy overrides verbatim from mcp_coder; deptry DEP003 =
`openai`, `anthropic`, `google`, `ollama`, `pydantic`. `langgraph` / `langchain-mcp-adapters` (in
mcp_coder's `langchain-base`) follow in #15 with the agent layer. Do not change these entries; only fix
them if a check proves one wrong.

`.importlinter` – add (keep `truststore_isolation` from Step 1):
```ini
# The copied model layer and the flat copies import no other agent_workbench module and never langgraph.
# import-linter skips a source/forbidden pair where one contains the other, so agent_workbench.* alone
# does not cover modules inside adapters: agent_workbench.adapters.* is forbidden as well.
[importlinter:contract:langchain_model_layer]
name = LangChain Model Layer Self-Contained
type = forbidden
source_modules =
    agent_workbench.adapters.langchain.<each of the 15 modules>
    agent_workbench.adapters.llm_types
    agent_workbench.adapters.config_hints
    agent_workbench.adapters.ssl_setup
    agent_workbench.adapters.toml_utils
forbidden_modules =
    agent_workbench.*
    agent_workbench.adapters.*
    langgraph
ignore_imports =
    agent_workbench.adapters.langchain._usage -> agent_workbench.adapters.llm_types
    agent_workbench.adapters.langchain._provider_checks -> agent_workbench.adapters.config_hints

[importlinter:contract:langchain_model_layer_ancestors]
name = LangChain Model Layer No Ancestor Imports
type = forbidden
as_packages = False
source_modules =
    <same 19 modules>
forbidden_modules =
    agent_workbench
    agent_workbench.adapters
    agent_workbench.adapters.langchain
```
Third-party contracts, one per module, all of this shape:
```ini
[importlinter:contract:<module>_isolation]
name = <module> only in adapters
type = forbidden
source_modules =
    agent_workbench
forbidden_modules =
    <module>
ignore_imports =
    agent_workbench.adapters.** -> <module>
```
for `langchain_core`, `langchain_openai`, `langchain_google_genai`, `langchain_anthropic`,
`langchain_ollama`, `openai`, `anthropic`, `google`, `ollama`, `httpx`, `mcp_coder_utils`
(`truststore` exists already). `mcp_coder_utils` gets its `agent_workbench.services.** -> mcp_coder_utils`
line in Step 7, when the first services import exists.
If a contract or an `ignore_imports` line fails because its module is not in the import graph (e.g.
`langgraph`), drop that entry, leave a comment `# dropped: <module> not in the import graph yet` and add
a line to `pr_info/pr_notes.md` under a heading `Dropped import-linter entries`.

`vulture_whitelist.py`: port mcp_coder's entries for the copied source modules, then whitelist every
further name `run_vulture_check` reports in them (names used only by the tests of Steps 3–4 included),
each with a comment naming the file.

`.large-files-allowlist`: run `check_file_size(max_lines=750)`; add any copied file over the limit
(copies stay unchanged).

## ALGORITHM
```
for each module in the list:
    text = git show f88e6b55:<path>
    save_file(dest, header + text with only the allowed rewrites)
update pyproject, .importlinter, vulture whitelist
run_format_code; run checks; fix only within the allowed changes
diff each copy against its git show output
```

## DATA
Defined by the copies, notably: `_setup._create_chat_model(config: Mapping[str, str | None], timeout: int = 30)`,
`_setup._handle_provider_error(exc, backend, dialed=None) -> None`,
`_provider_checks.check_provider(config, check_models=False) -> dict[str, Any]` (rows
`{"ok": bool | None, "value": str, "install_hint"?: str}`, `effective_config: list[tuple[str, str]]`,
`overall_ok: bool`), `_errors_404._is_404_error`, `_errors_404._format_404_hint(config: dict)`,
`_config_diagnostics.dialed_url(chat_model)`, `_exceptions.LLMAuthError`, `LLMConnectionError`,
`classify_connection_error`, `format_diagnostics`.

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports, vulture, deptry, tach,
check_file_size. One commit: `Copy the LangChain model layer from mcp_coder`.
