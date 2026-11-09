# Step 4 – Copy the model-layer tests, part 2: contract, diagnostics, models, provider checks, resolve_target

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step"), `pr_info/steps/step_3.md` (the
allowed test changes) and this file. Implement Step 4 only: copy the second half of mcp_coder's
model-layer tests (commit `f88e6b55`) into `tests/adapters/langchain/`, make all checks pass, and produce
exactly one commit. This is a mechanical copy: do not refactor the copies.

## Precondition
If `git show f88e6b55:<path>` fails for a listed file, write one line to `pr_info/.blocked.txt` naming the
file and stop.

## WHERE
`tests/llm/providers/langchain/test_langchain_{contract,diagnostics,models,models_ollama,provider_checks,resolve_target}.py`
→ `tests/adapters/langchain/` (the conftest exists from Step 3).

Modified: `vulture_whitelist.py` (only if needed), `.large-files-allowlist` (only if needed).

## WHAT
Test copies – the same allowed changes as in Step 3 ("WHAT", test copies), plus:
- `TestImportCycle` checks `_config_diagnostics.dialed_url` instead of the package attribute.
If a copied test still cannot pass within these changes, mark it `@pytest.mark.skip(reason="<why>")` and
add a line to `pr_info/pr_notes.md` under `Skipped copied tests`, as in Step 3.

## HOW
`vulture_whitelist.py`: port mcp_coder's entries for these tests, then whitelist every further name
`run_vulture_check` reports in them, each with a comment naming the file.
`.large-files-allowlist`: run `check_file_size(max_lines=750)`; add any copied test over the limit.

## ALGORITHM
```
for each test file in the list:
    text = git show f88e6b55:<path>
    save_file(dest, header + text with only the allowed rewrites)
run_format_code; run checks; fix only within the allowed changes
diff each copy against its git show output
```

## DATA
None new.

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports, vulture, check_file_size.
One commit: `Copy model-layer tests from mcp_coder (contract, diagnostics, models, provider checks)`.
