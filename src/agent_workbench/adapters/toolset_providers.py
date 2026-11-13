"""Toolset provider discovery through the ``agent_workbench.toolsets`` entry-point group.

A tool package registers its ``ToolsetProvider`` under the name of its config table
(``[tools.<name>]``). No module of agent_workbench imports a tool package; providers
are reached only through their entry points.
"""

from collections.abc import Iterable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import ToolsetProvider

ENTRY_POINT_GROUP = "agent_workbench.toolsets"


def registered_providers() -> list[str]:
    """Return the sorted names registered in the ``agent_workbench.toolsets`` group.

    Returns:
        The entry-point names, sorted.
    """
    return sorted(ep.name for ep in entry_points(group=ENTRY_POINT_GROUP))


def provider_class(name: str) -> type["ToolsetProvider"]:
    """Load the provider registered as *name*.

    Args:
        name: Entry-point name, i.e. the ``[tools.<name>]`` table name.

    Returns:
        The loaded provider class.

    Raises:
        ValueError: No entry point has the name (message lists the registered names and
            says to install the package that provides toolset '<name>'), or loading it
            fails.
    """
    registered = list(entry_points(group=ENTRY_POINT_GROUP))
    for entry_point in registered:
        if entry_point.name == name:
            try:
                cls: type[ToolsetProvider] = entry_point.load()
            except Exception as exc:
                raise ValueError(
                    f"Toolset provider '{name}' failed to load: {exc}"
                ) from exc
            return cls
    names = ", ".join(sorted(ep.name for ep in registered)) or "none"
    raise ValueError(
        f"Toolset provider '{name}' is not registered in the {ENTRY_POINT_GROUP} "
        f"entry-point group; registered: {names}. "
        f"To use [tools.{name}], install the package that provides toolset '{name}'."
    )


def provider_packages(names: Iterable[str]) -> list[str]:
    """Return the top-level package of each registered provider in *names*, without loading it.

    Args:
        names: Provider names; names without an entry point are skipped.

    Returns:
        The top-level package of each provider, in the order of *names*.
    """
    by_name = {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}
    return [
        by_name[name].value.split(":")[0].split(".")[0]
        for name in names
        if name in by_name
    ]
