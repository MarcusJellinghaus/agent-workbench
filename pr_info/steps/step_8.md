# Step 8 – Docs: README, architecture, security design

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_8.md`), and issue #18
(Scope "Docs"). Implement step 8 only: documentation, no code. Keep the docs' existing style
(short bullets, no filler). Run pytest (`extra_args: ["-n", "auto", "-m", "not integration"]`)
once to confirm nothing broke. One commit.

## WHERE
- `README.md`
- `docs/architecture/architecture.md`
- `docs/security/security_design.md`

## WHAT

### README.md
- "Status:" line: tools are `deny` unless `[permissions]` allows them.
- New `### Permissions` section after `### Tools`, with the default block (epic #13 "Default
  modes"; no example file is shipped):
  ```toml
  [permissions]
  "sql.schema" = "allow"
  validate_sql = "allow"
  "workspace.read" = "allow"
  "workspace.write" = "allow"
  ```
  Bullets: modes `allow` / `ask` (confirm each call) / `ask_session` (confirm once per tool
  per conversation; not kept across a reload, resume or restart) / `deny` (not shown to the
  model); tool-level entry beats group-level; unlisted tools are `deny`; without
  `[permissions]` every tool is `deny`; group names contain dots and must be quoted
  (`sql.schema = "allow"` is a nested table and an error); unknown names are a `verify`
  warning.
- `verify` "Sections:" line: add PERMISSIONS (effective mode and source per tool). Exit-code
  bullet: add the PERMISSIONS checks.
- `agent-workbench-ui` "Start:" bullet: the toolset build happens in `verify`'s PERMISSIONS
  check; a build error fails `verify` and stops the start.
- "Limits per turn" bullet: the 300 s timer is also paused while a confirmation dialog is open.
- New bullet: confirmation dialog – arguments message, OK / Cancel, 300 s timeout = Cancel,
  Stop cancels it.
- Tool-call log bullet: outcome list `ok`, `error`, `cancelled`, `denied`, `blocked`,
  `unknown_tool`, `invalid_arguments`, `dialog_error`.

### docs/architecture/architecture.md
- §4 "How a tool call works": order unbound → arguments validated → mode (`ask` /
  `ask_session` confirm in Chainlit) → run and log; the gate is `ToolNode(awrap_tool_call=...)`.
- §5 table:
  - core Responsibility keeps "permission modes"; Status adds `PermissionMode`.
  - services Responsibility: "Permission config and resolver, tool-call logging" (the check
    and dialog are in `apps`, epic #13 "Layers"; tool filter gone); Status: "verify checks
    (incl. PERMISSIONS), logging setup, permission parser / resolver, tool-call log".
  - apps Responsibility/Status: permission gate (`apps/permission_gate.py`) and Chainlit
    confirmation dialog; `agent-workbench-ui` "(toolset build gate)" → the build now happens
    in verify's PERMISSIONS check.
  - adapters: "toolset building (called from `apps` and `services.verify`)".
  - interfaces: "verify (incl. TOOLS, PERMISSIONS)".
  - Contracts list: `services.permissions` imports only `core`; `services.verify` does not
    import `adapters.tools`.
- §6 "Tool permissions (planned)" → "Tool permissions": drop "(planned)", "once per
  session" → "once per tool per conversation (not kept across a reload, resume or
  restart)", "Example defaults" → the README block (no example file); `[permissions]` table,
  quoting, interceptor, fail-closed cases, denial wording.
- §6 "Limits": the inactivity timer is also paused while a dialog is open.
- §6 tool-call log: outcome list; replace "Not logged: … until the permission node (#18)
  logs them" with: the gate logs calls that do not run (unknown / `deny` tool, invalid
  arguments, denied, dialog error, cancelled during a dialog).

### docs/security/security_design.md
- Status line: permissions implemented (drop "permissions planned").
- §3: the defaults are not shipped – without `[permissions]` every tool is `deny`; the
  README block lists the recommended defaults.
- §4.1:
  - "once per session" → "once per tool per conversation (not kept across a reload, resume
    or restart)".
  - "Defaults in the example config" → the README block (no example file).
  - The arguments message before each dialog is saved in `chainlit.sqlite` (detail in §5).
  - The outcomes of calls that don't run are in `tool_calls.jsonl`.
  - Fail closed: no dialog reachable, a failing dialog, a timeout → denied.
  - Reconnect during a dialog: the dialog is cleared in the page, Chainlit's
    `connection_successful` also hides Stop and reopens the input; a new message starts a
    second turn and Stop then reaches only that one; the old call is denied at the 300 s
    timeout (fail closed). Same exposure as #17's long tools.
- §4.6: the inactivity timer is also paused while a dialog is open.
- §5 Tool-call log row: one line per call incl. calls that do not run, with the outcome list.
- §5 Session database row: the arguments message and the ask text are stored in `chainlit.sqlite`.

## Tests
None (documentation only).
