"""Toolsets of the configured providers, and tool specs as LangChain tools.

Providers are found by entry point (``adapters.toolset_providers``); no tool package
is imported here. The ``tool_spec`` shim is imported only for type checking or inside
``build_toolsets``, since the core ``mcp-coder-utils`` floor has no tool contract.
"""

import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool

from agent_workbench.adapters.config import ConfigFile, tools_config_problems
from agent_workbench.adapters.tool_results import result_text
from agent_workbench.adapters.toolset_providers import provider_class

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import Toolset, ToolSpec

logger = logging.getLogger(__name__)


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


def to_structured_tool(spec: "ToolSpec") -> StructuredTool:
    """Return *spec* as a LangChain tool; a sync ``fn`` runs in LangChain's executor.

    The graph invokes tools only asynchronously, so a sync ``fn`` is passed as
    ``func`` and LangChain runs it in its executor instead of blocking the loop.

    Args:
        spec: The tool spec to convert.

    Returns:
        A ``StructuredTool`` with the spec's name, description and args model,
        whose result is the text from ``result_text``.
    """
    fn = spec.fn
    if inspect.iscoroutinefunction(fn):

        async def _acall(**kwargs: Any) -> str:
            return result_text(await fn(**kwargs))

        return StructuredTool(
            name=spec.name,
            description=spec.description,
            args_schema=spec.args_model,
            coroutine=_acall,
        )

    def _call(**kwargs: Any) -> str:
        return result_text(fn(**kwargs))

    return StructuredTool(
        name=spec.name,
        description=spec.description,
        args_schema=spec.args_model,
        func=_call,
    )
