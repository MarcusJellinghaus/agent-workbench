"""Hard-coded tool filter: the specs offered to the model until #18's permission resolver."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import ToolSpec

ENABLED_GROUPS: frozenset[str] = frozenset(
    {"sql.schema", "workspace.read", "workspace.write"}
)
ENABLED_TOOLS: frozenset[str] = frozenset(
    {"validate_sql"}
)  # its group also holds `verify`


def enabled_specs(specs: Iterable["ToolSpec"]) -> tuple["ToolSpec", ...]:
    """Return the specs offered to the model until #18's permission resolver replaces this.

    Args:
        specs: The specs of all configured toolsets.

    Returns:
        The specs in ``ENABLED_GROUPS`` or named in ``ENABLED_TOOLS``, order kept.
    """
    return tuple(
        spec
        for spec in specs
        if spec.group in ENABLED_GROUPS or spec.name in ENABLED_TOOLS
    )
