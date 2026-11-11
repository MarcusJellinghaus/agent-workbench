# Step 4 – `[tools]` config reading and validation

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_4.md`), then implement
this step only. Follow the existing `[llm]` handling in `adapters/config.py` and
`services/verify.py`. TDD: tests first. Run pylint, pytest (`-n auto -m "not integration"`)
and mypy; all must pass. One commit.

## WHERE
- `src/agent_workbench/adapters/config.py`
- `tests/adapters/test_config.py`

## WHAT
```python
TOOL_KEYS: dict[str, tuple[str, ...]] = {
    "sql": ("query_config", "database_config"),
    "workspace": ("project_dir",),
}
REQUIRED_TOOL_KEYS: dict[str, tuple[str, ...]] = {
    "sql": ("query_config",),
    "workspace": ("project_dir",),
}

@dataclass(frozen=True)
class ConfigFile:
    ...                                  # existing fields unchanged, in the same order
    tools: dict[str, Any] = field(default_factory=dict)
    tools_type_error: str | None = None

def tool_path(value: str) -> Path:
    """Return *value* as a path with ``~`` expanded."""

def tools_config_problems(config_file: ConfigFile) -> list[tuple[str, str, str]]:
    """Return ``(label, status, message)`` rows for every problem in ``[tools]``.

    status is "error" or "warning". Validating the files the paths point to is the
    tool package's job.
    """
```

## HOW
- `read_config_file`: after parsing, read `llm` and `tools` independently – a broken
  `[llm]` no longer returns before `[tools]` is read:
  `tools = data.get("tools", {})`; not a dict → `tools={}`,
  `tools_type_error=f"expected table, got {type(tools).__name__}"`. Same for `llm` as today.
  Construct `ConfigFile` with keyword arguments for the new fields.
- Update the `ConfigFile` docstring (two new attributes) and the module docstring
  (mentions `[tools]`).
- `#18` adds its table name to `TOOL_KEYS`' known subtables – note that in a comment.

## ALGORITHM (`tools_config_problems`)
```
if tools_type_error: return [("[tools]", "error", tools_type_error)]
for name, table in config_file.tools.items():
    label = f"[tools.{name}]"
    if name not in TOOL_KEYS: warning f"unknown table: {name}" (+ unknown_key_hint("tools", name, TOOL_KEYS)); continue
    if not dict: error "expected table, got <type>"; continue
    for key in REQUIRED_TOOL_KEYS[name] missing: error f"{key} missing"
    for key, value in table.items():
        unknown → warning f"unknown key: {key}" (+ unknown_key_hint(f"tools.{name}", key, TOOL_KEYS[name]))
        not str → error f"{key}: expected str, got {type} ('{value}')"
        not tool_path(value).is_absolute() → error f"{key}: relative path not allowed: {value}"
```
Messages start with the key name so `format_config_section` renders it as the row label.

## Tests (`tests/adapters/test_config.py`, write TOML to `tmp_path`)
- `[tools.sql]` / `[tools.workspace]` read into `ConfigFile.tools`; no `[tools]` → `{}`.
- `tools = "x"` → `tools_type_error`, `tools == {}`.
- broken `[llm]` (`llm = 1`) still reads `[tools]`.
- `tools_config_problems` (parametrized): valid absolute paths → `[]`; `~/q.toml` →
  no problem (expanded); relative path → error; non-string → error; missing required key →
  error; unknown key → warning; unknown subtable (`[tools.foo]`) → warning; subtable not a
  table → error; `tools_type_error` → one error row.
- `tool_path("~/x")` equals `Path.home() / "x"`.

## DATA
Problem row: `("[tools.sql]", "error", "query_config: relative path not allowed: q.toml")`.
