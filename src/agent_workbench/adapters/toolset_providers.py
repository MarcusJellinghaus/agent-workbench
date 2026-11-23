"""Toolset provider discovery and toolset building.

A tool package registers its ``ToolsetProvider`` under the name of its config table
(``[tools.<name>]``) in the ``agent_workbench.toolsets`` entry-point group. No module of
agent_workbench imports a tool package; providers are reached only through their entry
points. ``build_toolsets`` builds the toolset of every configured provider.

This module does not import ``langchain_core``, so ``services.verify`` can build the
toolsets without the ``[langchain-base]`` extra. The ``tool_spec`` shim is imported only
for type checking or inside ``build_toolsets``, since the core ``mcp-coder-utils`` floor
has no tool contract.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from agent_workbench.adapters.config import ConfigFile, tools_config_problems

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import Toolset, ToolsetProvider, ToolSpec

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "agent_workbench.toolsets"


@dataclass(frozen=True)
class Toolsets:
    """The tool specs of every configured provider plus the toolsets to close.

    Attributes:
        specs: The specs of all toolsets, in config order; names are unique.
        toolsets: The built toolsets, in config order.
    """

    specs: tuple["ToolSpec", ...]
    toolsets: tuple["Toolset", ...] = ()

    def close(self) -> None:
        """Close every toolset; a failing close is logged and the rest still close."""
        for toolset in self.toolsets:
            try:
                toolset.close()
            except Exception:
                logger.exception("Closing toolset %r failed", toolset)


def build_toolsets(config_file: ConfigFile) -> Toolsets:
    """Build the toolset of every ``[tools.<name>]`` provider; close with ``Toolsets.close``.

    Args:
        config_file: The read config file; each ``[tools.<name>]`` table is passed
            unchanged to the provider registered as ``<name>``.

    Returns:
        The merged specs and the built toolsets.

    Raises:
        ValueError: A ``[tools]`` shape error, an unregistered provider, a provider build
            error (``ValueError`` from ``build``) or a duplicate tool name across
            providers. Toolsets built before the error are closed.
    """
    # Lazy: the core mcp-coder-utils floor has no tool_spec.
    from agent_workbench.adapters.tool_spec import (  # pylint: disable=import-outside-toplevel
        ToolCollector,
    )

    errors = [
        f"{label} {message}"
        for label, status, message in tools_config_problems(config_file)
        if status == "error"
    ]
    if errors:
        raise ValueError("Invalid [tools] config: " + "; ".join(errors))
    collector = ToolCollector()
    built: list[Toolset] = []
    try:
        for name, table in config_file.tools.items():
            cls = provider_class(name)
            try:
                toolset = cls(table).build()
                built.append(toolset)
                for spec in toolset.specs:
                    collector.add(spec)
            except ValueError as exc:
                raise ValueError(f"[tools.{name}] {exc}") from exc
    except BaseException:
        Toolsets((), tuple(built)).close()
        raise
    return Toolsets(collector.specs, tuple(built))


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
