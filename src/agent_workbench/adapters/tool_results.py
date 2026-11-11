"""Tool result conversion; no ``langchain_core``, so services can size results with it."""

import json
from typing import Any


def result_text(result: Any) -> str:
    """Return the text the model receives for a tool result.

    ``str`` passes through; everything else (dict, list – also ``list[str]`` and empty
    lists – bool, …) becomes JSON. LangChain would pass a ``list[str]`` on as content
    blocks.

    Args:
        result: The raw return value of a tool function.

    Returns:
        The result as one string.
    """
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
