# Step 5 – Launcher: auth secret, removed cookie env vars, `allow_thread_sharing`

## LLM prompt
Read `pr_info/steps/summary.md` and issue #16 (section "Local user and auth secret"), then
implement this step (`pr_info/steps/step_5.md`) with TDD. One commit.

## Preconditions
- If Chainlit is newer than 2.12.0, re-check that `ensure_jwt_secret()` reads
  `CHAINLIT_AUTH_SECRET` from `os.environ` after the target is loaded. If not: write one line
  to `pr_info/.blocked.txt` and stop.

## WHERE
- `src/agent_workbench/apps/ui_launcher.py`
- `tests/apps/test_ui_env.py`

## WHAT
```python
AUTH_SECRET_FILE = "chainlit_auth_secret"
def _auth_secret(app_data: Path) -> str: ...   # read or create <app_data>/chainlit_auth_secret
# prepare_chainlit_env(app_data) additionally sets os.environ["CHAINLIT_AUTH_SECRET"]
```

## HOW
- `_REMOVED_ENV_VARS` gains `"CHAINLIT_COOKIE_SAMESITE"`, `"CHAINLIT_AUTH_COOKIE_PATH"`,
  `"CHAINLIT_AUTH_COOKIE_NAME"`; comment updated (auth cookie). The list stays stated only
  here. `DATABASE_URL` and `CHAINLIT_CUSTOM_AUTH` stay.
- `_CONFIG_TEMPLATE`: `allow_thread_sharing = false` inside the existing `[features]` table.
- Secret file under `app_data`, not under `chainlit/`.

## ALGORITHM
```
_auth_secret(app_data):
    path = app_data / AUTH_SECRET_FILE
    if path.exists(): return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48); path.write_text(secret, encoding="utf-8"); return secret
prepare_chainlit_env: secret = _auth_secret(app_data)
    if os.environ.get("CHAINLIT_AUTH_SECRET") not in (None, "", secret): logger.warning("Ignoring CHAINLIT_AUTH_SECRET: ...")  # no values
    os.environ["CHAINLIT_AUTH_SECRET"] = secret
```

## DATA
- `_auth_secret` → the secret string; file contents = the secret only.

## Tests (write first), `tests/apps/test_ui_env.py`
- First call creates the file and sets the env var; second call reuses it (same value).
- A different env value is overwritten by the stored one; a warning is logged that contains
  neither value.
- An env value equal to the stored one logs nothing.
- `test_unset_removed_env_vars_do_not_warn`: also pops `CHAINLIT_AUTH_SECRET` before its call.
- `test_removed_env_vars_dropped_with_warning` covers the three new vars automatically.
- `test_written_config_loaded_by_chainlit`: asserts `settings["features"].allow_thread_sharing is False`.
- All tests run inside `patch.dict(os.environ)` with `tmp_path` as app data.
