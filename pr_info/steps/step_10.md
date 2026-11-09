# Step 10 – Docs and final checks

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 10
only: update README, the architecture document and the CLAUDE.md pytest note, then run the full check
set. Produce exactly one commit.

## WHERE
- `README.md`
- `docs/architecture/architecture.md`
- `.claude/CLAUDE.md`

## WHAT
`README.md` – new sections (short, copy-pasteable, Windows first):
1. **Setup on Windows** – create the venv, `pip install -e ".[langchain]"` (or one provider extra, e.g.
   `".[langchain-openai]"`); `tools\reinstall_local.bat` for development.
2. **Configuration** – path `%USERPROFILE%\.agent_workbench\config.toml`; example:
   ```toml
   [llm]
   backend = "openai"        # openai | gemini | anthropic | ollama
   model = "gpt-4o-mini"
   # api_key = "..."         # prefer the vendor env var (OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY)
   # base_url = "https://host/v1"
   # api_version = "..."     # Azure OpenAI only
   ```
   Precedence: `AGENT_WORKBENCH_LLM_BACKEND` / `_MODEL` / `_BASE_URL` / `_API_VERSION` (empty = unset) →
   config.toml → unset; for the API key the vendor env var beats `api_key`. Nothing is read from a
   workspace folder. (The `verify` missing-file hint points to this section – keep its heading
   "Configuration".)
3. **`agent-workbench verify`** – sections, `--check-models` (advisory), exit codes, `--log-level DEBUG`.
4. **`agent-workbench prompt "<text>"`** – `--timeout` (default 60), exit code 1 with a message on any error.
Remove any mention of the greeting / `--name`.

`docs/architecture/architecture.md` §5:
- Status column: interfaces → `CLI: verify, prompt`; services → `verify checks, logging setup`;
  adapters → `copied LLM model layer, config loader, chat-model functions`; core → `LLMConfig`.
- Replace the "Placeholder code" subsection with one line: the placeholder was removed in #14.
- Correct the extras sentence to the extras that exist: `[langchain-openai]`, `[langchain-anthropic]`,
  `[langchain-gemini]`, `[langchain-ollama]`, meta `[langchain]` (later: `[sql]`, `[sql-mssql]`, `[workspace]`).

`.claude/CLAUDE.md`, section Code quality checks:
replace "No integration test markers yet — run everything." with
`extra_args: ["-n", "auto", "-m", "not integration"]` (integration tests need a real provider and run
only on request, with `markers=["integration"]`).

## HOW / ALGORITHM
```
edit the three files
run: pylint, pytest (-n auto -m "not integration"), mypy, ruff, lint-imports, tach, vulture, deptry,
     bandit, check_file_size(max_lines=750)
fix any finding (copies: only via whitelist / allowlist, never by editing them)
```

## DATA
None.

## Checks
All of the above. One commit: `Document setup, config, verify and prompt`.
