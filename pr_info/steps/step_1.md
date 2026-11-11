# Step 1 – Dependencies and extras

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`), then implement
this step only. Run pylint, pytest (`-n auto -m "not integration"`), mypy and
`tools/check_no_url_deps.py` (via the pytest/ruff MCP tools where possible); all must pass.
One commit.

## WHERE
- `pyproject.toml`

## WHAT
1. New extras in `[project.optional-dependencies]` (after the LangChain extras, with a
   `# Tool packages (#17), imported only when configured` comment):
   ```toml
   sql = ["mcp-tools-sql"]
   sql-mssql = ["mcp-tools-sql[mssql]"]
   workspace = ["mcp-workspace"]
   ```
   No version floors – #20 adds them once the siblings are released.
2. `dev`: `"agent-workbench[typecheck,coverage,langchain,sql,workspace]"`. Keep the
   `mcp-workspace` line (Claude Code MCP server) and its comment.
   Update the deptry comment: it names the self-referenced extras deptry does not expand.
3. `[tool.mcp-coder.install-from-github] packages` gains
   `"mcp-tools-sql @ git+https://github.com/MarcusJellinghaus/mcp-tools-sql.git"`
   (with deps, next to `mcp-workspace`). No URL in `[project]` dependencies
   (`tools/check_no_url_deps.py`).
4. mypy overrides, in the style of the existing ones:
   ```toml
   [[tool.mypy.overrides]]
   module = ["mcp_tools_sql", "mcp_tools_sql.*", "mcp_workspace", "mcp_workspace.*"]
   ignore_missing_imports = true
   follow_imports = "skip"  # optional extras; not installed in the typecheck job
   ```

## HOW
No source change. The import-linter contracts for the tool packages come with the first
import (step 6).

## Tests
None new – configuration only. Existing checks must pass; run
`tools/check_no_url_deps.py` (read it first for its invocation) and deptry
(`run_deptry_check`).

## DATA
n/a
