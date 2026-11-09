# Step 7 – Chainlit environment and `config.toml`

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 7: `adapters.config.app_data_dir`,
and in `apps/ui_launcher.py` the Chainlit environment cleanup and the `config.toml` writer,
plus the `tests/apps/conftest.py` that isolates Chainlit in tests. Probe first, tests next,
then code; all checks pass; one commit.

## Precondition
`chainlit` resolvable (`search_library_files(scope="chainlit", glob="__init__.py")`);
otherwise write one line to `pr_info/.blocked.txt` and stop.

## WHERE
- Modify `src/agent_workbench/adapters/config.py`, `tests/adapters/test_config.py`
- Create `src/agent_workbench/apps/ui_launcher.py` (this step: environment and config only)
- Create `tests/apps/conftest.py`, `tests/apps/test_ui_env.py`
- Modify `pyproject.toml` only if Chainlit's types fail mypy (override for `chainlit`,
  note it for the PR)

## WHAT
```python
# adapters/config.py
def app_data_dir() -> Path:
    """Return the user app-data folder (~/.agent_workbench)."""   # config_file_path() uses it

# apps/ui_launcher.py
CHAINLIT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
_REMOVED_ENV_VARS: tuple[str, ...] = (
    "DATABASE_URL", "LITERAL_API_KEY", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN",
    "SLACK_WEBSOCKET_TOKEN", "SLACK_SIGNING_SECRET", "TEAMS_APP_ID", "TEAMS_APP_PASSWORD",
    "CHAINLIT_CUSTOM_AUTH", "CHAINLIT_ROOT_PATH", "CHAINLIT_PARENT_ROOT_PATH",
    "CHAINLIT_SSL_CERT", "CHAINLIT_SSL_KEY",
    # + config-field env names found by the probe
)
_CONFIG_TEMPLATE = """..."""   # fixed TOML, str.format placeholders

def chainlit_port() -> int: ...                          # int(CHAINLIT_PORT) or DEFAULT_PORT
def prepare_chainlit_env(app_data: Path) -> Path: ...    # returns the app root
def write_chainlit_config(app_root: Path, port: int) -> Path: ...  # returns the file path
```

## HOW
- `ui_launcher.py` must not import Chainlit at module level (and nothing else in `apps`
  that does). The installed Chainlit version comes from
  `importlib.metadata.version("chainlit")`.
- `apps` may not import `mcp_coder_utils`: the launcher gets the folder from
  `adapters.config.app_data_dir()`.
- `_REMOVED_ENV_VARS` is the only list of these names (the conftest reuses the function).
- Config template (Chainlit merges nothing; missing keys take model defaults):
  ```toml
  [project]
  allow_origins = ["http://127.0.0.1:{port}", "http://localhost:{port}"]

  [features]
  edit_message = false

  [features.spontaneous_file_upload]
  enabled = false

  [features.mcp]
  enabled = false

  [UI]
  name = "agent-workbench"

  [meta]
  generated_by = "{version}"
  ```
  Build `allow_origins` from `origin_check.local_origins(port)` (e.g. `json.dumps` of the
  list) so origins are defined once. Comment in code: why `edit_message` is off (re-runs
  the handler outside the task Stop cancels; page and LangGraph thread out of step).
- Probes (`.scratch/`, set `CHAINLIT_APP_ROOT` to an existing temp folder and
  `CHAINLIT_ENV_FILE` to an absolute non-existent path before `import chainlit`):
  1. Chainlit's installed version (floor for step 8; the MCP keys above are those of 2.12.0);
  2. which env vars named like Chainlit's pydantic-settings config fields (e.g. `ROOT`,
     `RUN`, `CHAINLIT_SERVER`, case-insensitive) override the config → add each to
     `_REMOVED_ENV_VARS`;
  3. the attribute paths of `chainlit.config.load_settings()` for the checked values;
  4. that `run_chainlit` reads `CHAINLIT_HOST` / `CHAINLIT_PORT` from the environment.
  Delete `.scratch/` before committing.

## ALGORITHM
```
prepare_chainlit_env(app_data):
  root = app_data / "chainlit"; root.mkdir(parents=True, exist_ok=True)
  os.environ["CHAINLIT_APP_ROOT"] = str(root); os.environ["CHAINLIT_ENV_FILE"] = str(root / "no-env-file.env")
  for var in _REMOVED_ENV_VARS: if os.environ.pop(var, None) is not None: logger.warning("Ignoring %s …", var)
  host = os.environ.get("CHAINLIT_HOST"); if host and host != CHAINLIT_HOST: logger.warning(...)
  os.environ["CHAINLIT_HOST"] = CHAINLIT_HOST; return root
write_chainlit_config: mkdir root/.chainlit; write _CONFIG_TEMPLATE.format(...) to config.toml (utf-8); return path
```

## DATA
`prepare_chainlit_env` → app root `Path`; `write_chainlit_config` → path of `config.toml`.

## Tests
- `tests/apps/conftest.py`, at module level (runs in every xdist worker before test modules
  import Chainlit): `prepare_chainlit_env(Path(tempfile.mkdtemp(prefix="aw-chainlit-")))`.
  Docstring explains why it is module level, not a fixture.
- `tests/apps/test_ui_env.py` (each test under `patch.dict(os.environ)` so env changes are
  undone; `app_data` = `tmp_path`):
  - app root `<app_data>/chainlit` exists; `CHAINLIT_APP_ROOT` points to it;
    `CHAINLIT_ENV_FILE` is absolute, inside the app root, and not created;
  - every var in `_REMOVED_ENV_VARS` that was set is removed, with a warning per var (`caplog`);
  - `CHAINLIT_HOST=0.0.0.0` set → forced to `127.0.0.1` with a warning;
  - `chainlit_port()` default 8000, honours `CHAINLIT_PORT`;
  - config: `write_chainlit_config(Path(os.environ["CHAINLIT_APP_ROOT"]), 8123)` (the
    conftest's root – `load_settings()` reads the file fixed at the first Chainlit import),
    then `chainlit.config.load_settings()` has the two allowed origins, spontaneous uploads
    off, `edit_message` off, MCP off, UI name `agent-workbench`;
  - the repo root has no `.chainlit/` and no `.files/` after Chainlit was imported.
- `tests/adapters/test_config.py`: `config_file_path()` is `app_data_dir() / "config.toml"`.

## Checks / commit
pylint, pytest, mypy, ruff, lint-imports, vulture, deptry. Commit:
`feat(apps): isolate the Chainlit environment and config`.
