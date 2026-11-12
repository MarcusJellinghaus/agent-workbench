# Summary — Issue #28: CI: re-run mypy when mcp-coder-utils main changes

## Goal

When `mcp-coder-utils` `main` changes, its `notify-downstream.yml` sends a
`repository_dispatch` event (`event-type: upstream-main-updated`,
`client-payload: {"upstream": "mcp-coder-utils", "sha": ...}`). Today,
agent-workbench has no workflow that listens for it, so a breaking upstream
change shows up here only on our next push. This PR adds the receiver, a copy of
mcp_coder's `.github/workflows/upstream-compat-check.yml`, adapted to this repo.
It re-runs `mypy --strict src tests` against upstream `main`.

MarcusJellinghaus/mcp-coder-utils#67 (which adds agent-workbench to the dispatch
matrix) depends on this workflow being on `main`.

## Architectural / design changes

- **New CI entry point, no code changes.** A standalone workflow with no
  push/PR trigger; it runs only on `repository_dispatch`
  (`types: [upstream-main-updated]`) and `workflow_dispatch` (optional input
  `upstream`, default `'manual'`).
- **Job name carries the upstream:**
  `upstream-compat-${{ github.event.client_payload.upstream || github.event.inputs.upstream || github.event_name }}`.
  A run triggered by mcp-coder-utils, or a manual run with
  `upstream=mcp-coder-utils`, is named `upstream-compat-mcp-coder-utils`.
- **Install reuses the `ci.yml` mypy job pattern:** one
  `uv pip install --system "${SPECS[@]}" ".[typecheck]"` call, where `SPECS`
  comes from `python tools/read_github_deps.py --specs`
  (`[tool.mcp-coder.install-from-github].packages`: mcp-workspace,
  mcp-tools-py, mcp-coder-utils from git). Because the specs and the project
  are resolved in one call, uv keeps the git versions instead of PyPI ones. A red
  run therefore points at upstream, not at an install difference. This replaces
  the template's separate per-upstream install calls.
- **Check: mypy only.** The template's import-test step is dropped: this repo
  has no `tests/test_module_imports.py`. With a single check step, the template's
  `id: install` / `if:` guards are dropped too: a failed install already stops
  the job.
- **Kept from the template:** `permissions: contents: read`, actions pinned by
  SHA (same versions as `ci.yml`), setup-uv default cache (no `with:`),
  Python 3.11.
- **Accepted exposure:** `--specs` also installs mcp-workspace and mcp-tools-py
  from git `main`; a broken `main` there can turn this run red (same as
  `ci.yml`).

## Files

| Action | Path |
|---|---|
| Create | `.github/workflows/upstream-compat-check.yml` |

No Python source, tests, `pyproject.toml`, README or docs change.

## Testing

TDD does not apply: the change is a single workflow file with no Python logic,
and it has no push/PR trigger, so the PR's CI cannot exercise it. Its install
and mypy commands are already exercised by `ci.yml`'s `mypy` job.
Acceptance is checked after merge: Marcus triggers a manual run on `main` with
`upstream=mcp-coder-utils`. It must go green, and its job must be named
`upstream-compat-mcp-coder-utils`.

## Steps

1. `step_1.md` — create `.github/workflows/upstream-compat-check.yml`, format,
   commit.
