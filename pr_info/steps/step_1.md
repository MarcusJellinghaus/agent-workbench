# Step 1 – mypy overrides for the tool packages

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`), then implement
this step only. Run pylint, pytest (`-n auto -m "not integration"`) and mypy; all must
pass. One commit.

## WHERE
- `pyproject.toml`

## WHAT
mypy overrides, in the style of the existing ones:
```toml
[[tool.mypy.overrides]]
module = ["mcp_tools_sql", "mcp_tools_sql.*", "mcp_workspace", "mcp_workspace.*"]
ignore_missing_imports = true
follow_imports = "skip"  # optional extras, imported lazily on the tool path
```

## HOW
No source change. The extras `[sql]`, `[sql-mssql]`, `[workspace]`, their `dev` entries
and the `install-from-github` entry come with the first `src` import of the tool packages
(step 6): before that, deptry reports the new extras as unused (DEP002) and the CI
`deptry` job fails.

> **Superseded by steps 8 and 9 (plugin model):** `src` never imports the tool packages,
> so step 8 removes this override again. Step 9 adds the extras as install shortcuts
> (DEP002 ignore); no `dev` or `install-from-github` entry for `mcp-tools-sql`.

## Tests
None new – configuration only. Existing checks must pass.

## DATA
n/a
