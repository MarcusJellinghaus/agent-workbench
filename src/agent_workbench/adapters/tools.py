"""Tool specs as LangChain tools.

The tool packages (``mcp_tools_sql``, ``mcp_workspace``) are imported only inside
``build_toolsets``; ``ToolSpec`` is imported only for type checking, since the core
``mcp-coder-utils`` floor has no ``tool_spec``.
"""

import inspect
from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool

from agent_workbench.adapters.tool_results import result_text

if TYPE_CHECKING:
    from agent_workbench.adapters.tool_spec import ToolSpec


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
