"""Tool contract shim — re-exports from mcp_coder_utils.

Import only under TYPE_CHECKING or lazily on the tool path: the core
``mcp-coder-utils>=0.1.6`` floor has neither ``tool_spec`` nor ``tool_provider``.
"""

from mcp_coder_utils.tool_provider import StaticToolset, Toolset, ToolsetProvider
from mcp_coder_utils.tool_spec import ToolCollector, ToolSpec

__all__ = [
    "StaticToolset",
    "ToolCollector",
    "ToolSpec",
    "Toolset",
    "ToolsetProvider",
]
