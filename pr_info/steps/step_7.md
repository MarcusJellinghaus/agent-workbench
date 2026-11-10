# Step 7 – Docs: README, security design, architecture

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (section "Docs" and the Decisions table),
then implement this step (`pr_info/steps/step_7.md`). Docs only; run the file-size check
and the full check suite once. One commit.

## WHERE
- `README.md`
- `docs/security/security_design.md`
- `docs/architecture/architecture.md`

## WHAT
README, section `agent-workbench-ui`:
- Start line: the startup check now also covers `langgraph.checkpoint.sqlite`, `greenlet`,
  `aiohttp`.
- Removed Chainlit env vars: add the auth-cookie vars.
- New "Sessions" bullets: stored in `%USERPROFILE%\.agent_workbench\sessions\`
  (`checkpoints.sqlite`, `chainlit.sqlite`, with SQLite's `-wal` / `-shm` side files);
  delete those files only with the app stopped; sign-in is automatic as the OS user; the
  sidebar lists at most 1000 conversations – older ones are not listed and cannot be
  deleted in the UI; token totals restart at 0 after a resume; thumbs buttons are visible
  but feedback is out of scope; conversations are kept until deleted.

`docs/security/security_design.md`:
- §2: identity / network – header auth signs in anything that reaches `127.0.0.1:<port>`.
- §4.5: `<app-data>/chainlit_auth_secret` is a credential (generated, reused, wins over the
  env var); the auth-cookie env vars are removed.
- §4.7: new dependencies; `aiohttp` is imported only by Chainlit's data layer, never by our code.
- §5: sessions on disk in `<app-data>/sessions/` (two SQLite files, WAL); feedback ratings
  and comments can be stored and are deleted with the thread; `secure_delete` and the WAL
  checkpoint after a delete, and their limits (journal / WAL files removed by SQLite are not
  wiped at file-system level); replace "until #16, sessions live only in memory".
- §6: row 9 residual risk – any local process (on a shared Windows host also other OS
  users) can read stored conversations through the page; the origin check only stops
  browsers; accepted for M1. Update other rows only where #16 changes them.

`docs/architecture/architecture.md`:
- §5 core-dependencies line: `sqlalchemy[asyncio]`, `aiosqlite`, `aiohttp`; the
  `[langchain-base]` sentence names the SQLite checkpointer.
- "Third-party dependencies per layer": `apps` adds `sqlalchemy`, `aiosqlite`.
- Building Block table, `apps` status: + sessions (save, list, resume, delete).
- §6 "Logging and retention (planned)": the session part is implemented (where, secure
  delete); the tool-call log stays planned.

## HOW
- Keep the existing writing style: short bullets, no restating of the issue.
- `check_file_size` must pass.

## Checks
pytest, ruff, pylint, mypy, lint-imports, vulture, deptry; tach only if it fails.
