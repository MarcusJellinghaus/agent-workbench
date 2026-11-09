# Step 1 – Flat copies: `llm_types`, `config_hints`, `ssl_setup`, `toml_utils`

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 1
only: copy four mcp_coder modules (commit `f88e6b55`) flat into `src/agent_workbench/adapters/` together
with their copied tests, make all checks pass, and produce exactly one commit.

## WHERE
| Source (mcp_coder, `f88e6b55`) | Destination |
|---|---|
| `src/mcp_coder/llm/types.py` | `src/agent_workbench/adapters/llm_types.py` |
| `src/mcp_coder/utils/config_hints.py` | `src/agent_workbench/adapters/config_hints.py` |
| `src/mcp_coder/utils/ssl_setup.py` | `src/agent_workbench/adapters/ssl_setup.py` |
| `src/mcp_coder/utils/toml_utils.py` | `src/agent_workbench/adapters/toml_utils.py` |
| `tests/utils/test_config_hints.py` | `tests/adapters/test_config_hints.py` |
| `tests/utils/test_ssl_setup.py` | `tests/adapters/test_ssl_setup.py` |
| class `TestFormatTomlError` (+ the imports it needs) from `tests/utils/test_user_config.py` | `tests/adapters/test_toml_utils.py` |

New: `tests/adapters/__init__.py` (empty).
Modified: `pyproject.toml`, `.importlinter`, `vulture_whitelist.py`.

## WHAT
Whole files, unchanged except:
- the header comment line (see summary);
- module paths in tests: `mcp_coder.utils.<m>` / `mcp_coder.llm.types` → `agent_workbench.adapters.<m>`,
  in imports, `patch(...)` targets (including f-string-built ones) and logger-name strings;
- the import-order re-sort applied by `run_format_code`.
Section names passed as test input (e.g. `"llm.langchain"` in `test_config_hints`) stay unchanged.
Assertions are unchanged.

Public names kept: `ensure_truststore()` (ssl_setup), `format_toml_error(path, exc)` (toml_utils),
`suggest(name, candidates)`, `unknown_key_hint(section, key, known_keys)` (config_hints), all TypedDicts /
constants of `llm_types`.

## HOW
- `pyproject.toml`
  - `dependencies = ["truststore>=0.9.0"]` (first runtime dependency; `ssl_setup` imports it).
  - `[tool.mypy]`: add `disable_error_code = ["import-untyped"]`.
  - overrides: `module = ["truststore"]` → `ignore_missing_imports = true`;
    add `ignore_missing_imports = true` to the existing `tests.*` override.
- `.importlinter`: add
  ```ini
  # truststore: process-wide injection (adapters.ssl_setup) and the per-client SSL context of the
  # copied model layer. Allowed in adapters only.
  [importlinter:contract:truststore_isolation]
  name = truststore only in adapters
  type = forbidden
  source_modules =
      agent_workbench
  forbidden_modules =
      truststore
  ignore_imports =
      agent_workbench.adapters.** -> truststore
  ```
- `vulture_whitelist.py`: port mcp_coder's entries that belong to these files
  (`_.cache_creation_input_tokens` for `llm_types`, `_._reset_injected` for `test_ssl_setup`), then run
  `run_vulture_check` and whitelist every further name it reports in the four copies / three tests, each
  with a one-line comment naming the file. The copies are not edited for vulture.

## ALGORITHM
```
for each (source, dest) above:
    text = git show f88e6b55:<source>
    save_file(dest, header + text with only the allowed path rewrites)
run_format_code; run all checks; compare each copy with its git show output
```

## DATA
No new data structures – the copies define them (`llm_types` TypedDicts, `_RENAME_HINTS`, …).

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports, vulture, deptry
(`run_deptry_check` – `truststore` must not be DEP002). One commit:
`Copy llm_types, config_hints, ssl_setup and toml_utils from mcp_coder`.
