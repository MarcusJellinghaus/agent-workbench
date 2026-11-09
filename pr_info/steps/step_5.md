# Step 5 – Config: `LLMConfig` type and the config file reader / loader

## LLM prompt
Read `pr_info/steps/summary.md` (especially "Rules for every step") and this file. Implement Step 5
only, test first: the `LLMConfig` type in `core` and the config reader / loader in `adapters`. Make all
checks pass and produce exactly one commit.

## WHERE
- New `src/agent_workbench/core/config.py`
- New `src/agent_workbench/adapters/config.py`
- New tests `tests/core/test_config.py`, `tests/adapters/test_config.py`

## WHAT
`core/config.py` (standard library only):
```python
LLM_KEYS: tuple[str, ...] = ("backend", "model", "api_key", "base_url", "api_version")

@dataclass(frozen=True)
class LLMConfig:
    """The [llm] section: keys of mcp_coder's [llm.langchain]."""
    backend: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a real dict with exactly the five keys (the copied functions need a dict)."""
```

`adapters/config.py`:
```python
ENV_VARS: dict[str, str] = {
    "backend": "AGENT_WORKBENCH_LLM_BACKEND",
    "model": "AGENT_WORKBENCH_LLM_MODEL",
    "base_url": "AGENT_WORKBENCH_LLM_BASE_URL",
    "api_version": "AGENT_WORKBENCH_LLM_API_VERSION",
}  # no app env var for api_key: the vendor env var beats config inside the copied backends

@dataclass(frozen=True)
class ConfigFile:
    path: Path
    exists: bool
    parse_error: str | None   # format_toml_error(...) text, or the OSError text
    llm: dict[str, Any]       # raw [llm] table; {} when absent / unreadable

def config_file_path() -> Path: ...           # get_user_app_data_dir("agent_workbench") / "config.toml"
def read_config_file(path: Path | None = None) -> ConfigFile: ...
def wrong_type_keys(llm: Mapping[str, Any]) -> list[str]: ...   # known keys whose value is not str
def load_llm_config(config_file: ConfigFile | None = None) -> LLMConfig: ...   # never raises
```

## HOW
- `from mcp_coder_utils.user_app_data import get_user_app_data_dir` (allowed in adapters by the
  `mcp_coder_utils_isolation` contract from Step 2).
- `from agent_workbench.adapters.toml_utils import format_toml_error`.
- `from agent_workbench.core.config import LLM_KEYS, LLMConfig`.
- `read_config_file(None)` calls `config_file_path()` at call time, so tests patch
  `agent_workbench.adapters.config.config_file_path` or pass a `tmp_path` file.
- Logging: `logger = logging.getLogger(__name__)`; warnings name the CONFIG section of
  `agent-workbench verify`.

## ALGORITHM
```
read_config_file(path):
    path = path or config_file_path(); if not path.exists(): return ConfigFile(path, False, None, {})
    try data = tomllib.load(open(path, "rb"))
    except TOMLDecodeError as e: return ConfigFile(path, True, format_toml_error(path, e), {})
    except OSError as e: return ConfigFile(path, True, f"Error reading config file: {path}\n{e}", {})
    llm = data.get("llm", {})
    if not isinstance(llm, dict): return ConfigFile(path, True, f"[llm] must be a table, got {type(llm).__name__}", {})
    return ConfigFile(path, True, None, llm)

load_llm_config(cf):
    cf = cf or read_config_file()
    if cf.parse_error or wrong_type_keys(cf.llm): logger.warning(...); return LLMConfig()   # all unset
    env = {k: os.environ.get(var) or None for k, var in ENV_VARS.items()}            # "" -> unset
    return LLMConfig(**{k: env.get(k) or cf.llm.get(k) for k in LLM_KEYS})          # env > file > unset; unknown keys ignored
```
`[llm]` that is not a table (e.g. `llm = 5`) is reported through `parse_error`, so loader and `verify`
treat it like invalid TOML – no extra code path.

## DATA
- `LLMConfig().as_dict()` → `{"backend": None, "model": None, "api_key": None, "base_url": None, "api_version": None}`.
- `ConfigFile` as above. Missing file → env vars still apply; invalid TOML / wrong type → `LLMConfig()`.

## Tests (write first)
`tests/core/test_config.py`: `as_dict()` returns a `dict` with exactly `LLM_KEYS`, values copied.

`tests/adapters/test_config.py` (fixture: `monkeypatch.delenv` every `ENV_VARS` value, `raising=False`;
config files written to `tmp_path`):
- file values loaded (all five keys);
- env var overrides the file value;
- empty env var counts as unset (file value wins);
- missing file → `exists False`, env var still applies, else all `None`;
- invalid TOML → `parse_error` contains `format_toml_error` text, loader returns `LLMConfig()`, warning in `caplog`;
- wrong type (`model = 123`) → `wrong_type_keys == ["model"]`, loader returns `LLMConfig()` even with an env var set, warning logged;
- unknown key ignored by the loader;
- `config_file_path()` ends with `.agent_workbench/config.toml` (patch `Path.home` or assert the parts).

## Checks
pylint, pytest (`-n auto -m "not integration"`), mypy, ruff, lint-imports. One commit:
`Add the [llm] config type and loader`.
