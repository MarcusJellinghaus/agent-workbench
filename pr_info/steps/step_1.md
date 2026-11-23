# Step 1 – Permission model: mode type, `[permissions]` reader, parser / resolver

## LLM prompt
Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`), and issue #18
(Scope "Config" and "Parser and resolver"). Implement step 1 only, test first: write the
tests below, then the code, then run pylint, pytest
(`extra_args: ["-n", "auto", "-m", "not integration"]`), mypy and lint-imports until all pass.
One commit.

## WHERE
- New `src/agent_workbench/core/permissions.py`
- New `src/agent_workbench/services/permissions.py`
- `src/agent_workbench/adapters/config.py`
- `.importlinter`
- Tests: new `tests/core/test_permissions.py`, new `tests/services/test_permissions.py`,
  `tests/adapters/test_config.py`

## WHAT

`core/permissions.py`:
```python
PermissionMode = Literal["allow", "ask", "ask_session", "deny"]
PERMISSION_MODES: tuple[PermissionMode, ...] = ("allow", "ask", "ask_session", "deny")
```

`adapters/config.py` – `ConfigFile` gains two fields with defaults, after `tools_type_error`:
```python
permissions: dict[str, Any] = field(default_factory=dict)
permissions_type_error: str | None = None
```
`read_config_file` fills them with `_table(data, "permissions")` (same parsed document; no
second `tomllib` read). Module docstring: mention `[permissions]`.

`services/permissions.py` (pure, no I/O; imports only `core` and the standard library):
```python
ProblemRow = tuple[str, str, str]          # (label, status, message), like tools_config_problems
LABEL = "[permissions]"

@dataclass(frozen=True)
class PermissionConfig:
    entries: Mapping[str, PermissionMode] = field(default_factory=dict)  # valid entries only

    def mode_of(self, tool: str, group: str) -> tuple[PermissionMode, str]:
        """Return (mode, source); source is "tool", "group" or "unlisted"."""

def parse_permissions(
    table: Mapping[str, Any],
    type_error: str | None,
    tools: Mapping[str, str],   # tool name -> group of every configured spec
) -> tuple[PermissionConfig, list[ProblemRow]]:
```

## ALGORITHM
`mode_of`: tool in entries → (entries[tool], "tool"); group in entries → (entries[group],
"group"); else ("deny", "unlisted"). No group expansion: a group is the single `spec.group`.

`parse_permissions`:
```
if type_error: return PermissionConfig(), [(LABEL, "error", type_error)]
if not table: rows.append((LABEL, "warning", "no entries – every tool is deny"))
groups = set(tools.values())
for key, value in table.items():
    dict value   -> error "<key>: unquoted dotted key – quote group names: \"<key>.<sub>\" = ..." (one per sub-key list); skip
    value not in PERMISSION_MODES -> error "<key>: unknown mode '<value>' (allow, ask, ask_session, deny)"; skip
    key in tools and key in groups -> error "<key>: is both a tool name and a group name"
    key in neither -> warning "<key>: names no tool or group of the configured providers – the entry has no effect"
    else entries[key] = value
return PermissionConfig(entries), rows
```
Every message starts with the key, so `verify_formatting.format_config_section` renders the
key as the row label.

## HOW
`.importlinter` – new contract (wildcard `services.*` because import-linter skips pairs where
one module contains the other; the resolver takes plain strings, not `ToolSpec`, since
`TYPE_CHECKING` imports count):
```ini
# The permission parser and resolver are pure: core and the standard library only.
[importlinter:contract:permissions_pure]
name = services.permissions imports only core
type = forbidden
source_modules =
    agent_workbench.services.permissions
forbidden_modules =
    agent_workbench.adapters
    agent_workbench.interfaces
    agent_workbench.apps
    agent_workbench.services.*
    langchain_core
    langgraph
    chainlit
```

## DATA
- `PermissionConfig.entries`: `{key: mode}` of the valid entries.
- Rows: `("[permissions]", "error" | "warning", message)`.

## Tests (write first)
- `tests/core/test_permissions.py`: `PERMISSION_MODES` equals the four modes in order.
- `tests/adapters/test_config.py`: `[permissions]` table is read (quoted dotted key kept as
  one key); absent → `{}`; `permissions = "x"` → `{}` and `permissions_type_error` set.
- `tests/services/test_permissions.py` (parametrize where possible):
  - `mode_of`: tool-level entry beats group-level; group-level applies; unlisted → `("deny", "unlisted")`.
  - unknown mode → error; type error → single error row and empty config.
  - `{"sql": {"schema": "allow"}}` → error containing "quote group names" and `"sql.schema"`.
  - key that is both a tool and a group name → error.
  - unknown tool name and unknown group name → warning containing "has no effect", not error.
  - empty table → the "every tool is deny" warning.
  - valid entries land in `entries`; invalid ones do not.
