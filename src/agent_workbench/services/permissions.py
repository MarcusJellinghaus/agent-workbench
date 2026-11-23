"""``[permissions]`` parser and resolver. Pure: no I/O, imports only ``core``.

Keys are tool names or group names (a group is the single ``ToolSpec.group`` string, no
nesting). A tool-level entry beats a group-level one; unlisted tools are ``deny``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_workbench.core.permissions import PERMISSION_MODES, PermissionMode

ProblemRow = tuple[
    str, str, str
]  # (label, status, message), like tools_config_problems
LABEL = "[permissions]"

ModeSource = Literal["tool", "group", "unlisted"]


@dataclass(frozen=True)
class PermissionConfig:
    """The valid ``[permissions]`` entries.

    Attributes:
        entries: ``{tool or group name: mode}`` of the valid entries only.
    """

    entries: Mapping[str, PermissionMode] = field(default_factory=dict)

    def mode_of(self, tool: str, group: str) -> tuple[PermissionMode, ModeSource]:
        """Resolve the mode of a tool.

        Args:
            tool: The tool name.
            group: The tool's group (``ToolSpec.group``).

        Returns:
            ``(mode, source)``; source is ``"tool"``, ``"group"`` or ``"unlisted"``.
        """
        if tool in self.entries:
            return self.entries[tool], "tool"
        if group in self.entries:
            return self.entries[group], "group"
        return "deny", "unlisted"


def _dotted_paths(prefix: str, table: Mapping[str, Any]) -> list[str]:
    """Return the full dotted path of every non-table value in *table*, any depth."""
    paths: list[str] = []
    for key, value in table.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            paths.extend(_dotted_paths(path, value))
        else:
            paths.append(path)
    return paths


def _nested_table_message(key: str, sub_table: Mapping[str, Any]) -> str:
    """Return the error for a key whose value is a table instead of a mode.

    TOML parses an unquoted dotted key (``sql.schema = "allow"``) and a key with an
    inline table (``"sql" = { schema = "allow" }``) to the same nested table, so the
    message names neither and suggests the quoted group name for each leaf.
    """
    paths = _dotted_paths(key, sub_table)
    if not paths:
        return f"{key} is a table, not a mode"
    quoted = ", ".join(f'"{path}" = ...' for path in paths)
    return f"{key} is a nested table, not a mode – quote group names: {quoted}"


def parse_permissions(
    table: Mapping[str, Any],
    type_error: str | None,
    tools: Mapping[str, str],
) -> tuple[PermissionConfig, list[ProblemRow]]:
    """Parse the raw ``[permissions]`` table.

    Every row is labelled ``LABEL``. A message about one key starts with that key and a
    space; the type-error and the empty-table messages name no key. Erroneous keys
    never land in the config.

    Args:
        table: The raw ``[permissions]`` table.
        type_error: Set when ``[permissions]`` is present but not a table.
        tools: ``{tool name: group}`` of every configured spec.

    Returns:
        The config of the valid entries and the problem rows.
    """
    if type_error:
        return PermissionConfig(), [(LABEL, "error", type_error)]
    rows: list[ProblemRow] = []
    if not table:
        rows.append((LABEL, "warning", "no entries – every tool is deny"))
    groups = set(tools.values())
    entries: dict[str, PermissionMode] = {}
    for key, value in table.items():
        if isinstance(value, dict):
            rows.append((LABEL, "error", _nested_table_message(key, value)))
        elif not isinstance(value, str) or value not in PERMISSION_MODES:
            rows.append(
                (
                    LABEL,
                    "error",
                    f"{key} has an unknown mode '{value}' "
                    f"({', '.join(PERMISSION_MODES)})",
                )
            )
        elif key in tools and key in groups:
            rows.append((LABEL, "error", f"{key} is both a tool name and a group name"))
        elif key not in tools and key not in groups:
            rows.append(
                (
                    LABEL,
                    "warning",
                    f"{key} names no tool or group of the configured providers "
                    "– the entry has no effect",
                )
            )
        else:
            entries[key] = value
    return PermissionConfig(entries), rows
