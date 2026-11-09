# Step 3 – Copy the model-layer tests, part 1: conftest, backends, http, exceptions, messages

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 3
only: copy the trimmed conftest and the first half of mcp_coder's model-layer tests (commit `f88e6b55`)
into `tests/adapters/langchain/`, make all checks pass, and produce exactly one commit.
This is a mechanical copy: do not refactor the copies or the source modules of Step 2.

## Precondition
If `git show f88e6b55:<path>` fails for a listed file, write one line to `pr_info/.blocked.txt` naming the
file and stop.

## WHERE
`tests/llm/providers/langchain/test_langchain_{anthropic,gemini,ollama,openai,http,exceptions,messages}.py`
→ `tests/adapters/langchain/`, plus `tests/adapters/langchain/__init__.py` (empty) and a trimmed
`tests/adapters/langchain/conftest.py` (from `tests/llm/providers/langchain/conftest.py`).

Modified: `vulture_whitelist.py` (only if needed).

## WHAT
Test copies – only these changes:
- header comment line;
- module paths in any form (imports, `patch(...)` targets incl. f-string-built ones, `caplog` logger
  names, `_LOGGER_NAME`, module-name constants): `mcp_coder.llm.providers.langchain` →
  `agent_workbench.adapters.langchain`, `mcp_coder.llm.types` → `agent_workbench.adapters.llm_types`,
  `mcp_coder.utils.config_hints` → `agent_workbench.adapters.config_hints`,
  `mcp_coder.utils.log_utils` → `mcp_coder_utils.redaction`;
- imports of names the mcp_coder package `__init__` re-exports (`_create_chat_model`,
  `_handle_provider_error`) point to `agent_workbench.adapters.langchain._setup`;
- every patch target names the module where agent-workbench looks the name up (a patch on the package
  attribute `agent_workbench.adapters.langchain.<name>` would pass silently – retarget it to the module
  that does the lookup);
- literals rendering a `_product` value (e.g. `[llm.langchain]` → `[llm]`, `mcp-coder[langchain]` →
  `agent-workbench[langchain]` in expected messages);
- import-order re-sort.
If a copied test still cannot pass within these changes, mark it
`@pytest.mark.skip(reason="<why>")` and add a line `- <test id>: <reason>` to
`pr_info/pr_notes.md` under a heading `Skipped copied tests` (for the PR description).

`conftest.py`: keep the module docstring, `_is_installed` and the session-scoped autouse
`_mock_langchain_modules` unchanged; drop `_tmp_home`, `skip_langchain_history_guard`, `graph_events`,
`async_events` and imports only they used.

## HOW
`vulture_whitelist.py`: port mcp_coder's entries for these tests and the conftest
(e.g. `_._mock_langchain_modules`, `_._clear_env` if a copied test defines it), then whitelist every
further name `run_vulture_check` reports in them, each with a comment naming the file.

## ALGORITHM
```
for each test file in the list (and conftest):
    text = git show f88e6b55:<path>
    save_file(dest, header + text with only the allowed rewrites)
run_format_code; run checks; fix only within the allowed changes
diff each copy against its git show output
```

## DATA
None new.

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports, vulture. One commit:
`Copy model-layer tests from mcp_coder (backends, http, exceptions, messages)`.
