# agent-workspace

Governed LLM chat workbench: configurable tool access, per-user permissions and audit logging.

Status: repo skeleton. See [docs/architecture/architecture.md](docs/architecture/architecture.md)
for the design and roadmap.

## Development setup (Windows)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bat
tools\reinstall_local.bat
```

This creates `.venv`, installs the package in editable mode with the `dev` extra
(pytest, mypy, pylint, ruff, import-linter, tach, vulture, deptry, mcp-coder and its MCP
servers) and activates the venv. On Linux/macOS: `source tools/reinstall_local.sh`.

Run the placeholder CLI:

```bat
agent-workspace --name you
```

## Quality checks

| Check | Command |
|---|---|
| Tests | `pytest` |
| Types | `tools\mypy.bat` |
| Lint | `tools\ruff_check.bat`, `tools\pylint_check_for_errors.bat` |
| Format | `ruff format src tests tools` |
| Layering | `tools\lint_imports.bat`, `tools\tach_check.bat` |
| Dead code | `tools\vulture_check.bat` |
| Dependencies | `tools\deptry_check.bat` |

CI runs all of them (`.github/workflows/ci.yml`).

## Working with Claude Code

This repo uses [mcp-coder](https://github.com/MarcusJellinghaus/mcp_coder) workflows.
Start Claude Code with `claude.bat` (sets up the MCP servers from `.mcp.json`).
Project instructions: [.claude/CLAUDE.md](.claude/CLAUDE.md).
