# Step 1 — Add `upstream-compat-check.yml` receiver workflow

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
> Create the one workflow file described below, run the formatter and make
> exactly one commit. Do not touch any other file.

## Preconditions

- If `.github/workflows/upstream-compat-check.yml` already exists, write one
  line to `pr_info/.blocked.txt` and stop.
- If `tools/read_github_deps.py` has no `--specs` mode, or
  `pyproject.toml` `[tool.mcp-coder.install-from-github].packages` does not
  list `mcp-coder-utils`, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- Create: `.github/workflows/upstream-compat-check.yml`
- Reference only (do not modify): `.github/workflows/ci.yml` (mypy job, action
  SHAs), mcp_coder `.github/workflows/upstream-compat-check.yml` (template).

## WHAT

One workflow, one job:

- Workflow `name: Upstream compat check`
- Triggers: `repository_dispatch` (`types: [upstream-main-updated]`),
  `workflow_dispatch` (input `upstream`, optional, default `'manual'`)
- `permissions: contents: read`
- Job `upstream-compat`, `runs-on: ubuntu-latest`, name
  `upstream-compat-${{ github.event.client_payload.upstream || github.event.inputs.upstream || github.event_name }}`
- Steps: checkout → setup-uv → setup-python 3.11 →
  "Install upstream packages from main and agent-workbench" →
  "Run mypy --strict"

## HOW

- Action SHAs must be identical to those in `ci.yml`. If `ci.yml`'s differ
  from the ones below, use `ci.yml`'s:
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`
  - `astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3`
  - `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0`
- setup-uv: no `with:` block (default cache, as in mcp_coder).
- No `id:` on the install step, no `if:` on the mypy step.
- No `mypy --version` prefix, no "Environment info" step.

## ALGORITHM

```
on dispatch/manual run:
  checkout repo; install uv; set up Python 3.11
  SPECS = lines of `python tools/read_github_deps.py --specs`   # git main specs
  uv pip install --system SPECS... ".[typecheck]"               # one call → git versions win
  mypy --strict src tests                                       # red on upstream break
```

## DATA

Exact file content:

```yaml
name: Upstream compat check

# Triggered by repository_dispatch when mcp-coder-utils' main branch changes.
# Runs mypy --strict against the latest mcp-coder-utils main to detect
# interface breaks.
# On failure: standard GitHub Actions email + red icon in the Actions tab.

on:
  repository_dispatch:
    types: [upstream-main-updated]
  workflow_dispatch:
    inputs:
      upstream:
        description: 'Upstream that triggered this run (shown in the job name)'
        required: false
        default: 'manual'

permissions:
  contents: read

jobs:
  upstream-compat:
    name: upstream-compat-${{ github.event.client_payload.upstream || github.event.inputs.upstream || github.event_name }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: 3.11

      # Upstream specs come from [tool.mcp-coder.install-from-github] and are
      # installed in the same call as .[typecheck], so uv keeps the git versions.
      - name: Install upstream packages from main and agent-workbench
        run: |
          mapfile -t SPECS < <(python tools/read_github_deps.py --specs)
          uv pip install --system "${SPECS[@]}" ".[typecheck]"

      - name: Run mypy --strict
        run: mypy --strict src tests
```

## Tests

None. The change has no Python logic, and the workflow has no push/PR trigger,
so neither pytest nor the PR's CI can exercise it. Acceptance is checked after
merge with a manual `workflow_dispatch` run (`upstream=mcp-coder-utils`).
The run must go green, and its job must be named `upstream-compat-mcp-coder-utils`.

## Checks

- Run `mcp__mcp-tools-py__run_format_code` (required before every commit).
- pylint, pytest and mypy are not affected (no Python touched). Running them is
  optional.

## Commit

One commit containing only `.github/workflows/upstream-compat-check.yml`:

```
ci: re-run mypy when mcp-coder-utils main changes (#28)
```
