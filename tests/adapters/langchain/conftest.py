# Copied from mcp_coder tests/llm/providers/langchain/conftest.py at commit f88e6b55 (MarcusJellinghaus/mcp_coder#1400).
"""conftest.py for langchain provider tests.

Injects sys.modules mocks so unit tests run without langchain installed.
Only injects mocks when the real packages are genuinely absent (ImportError).
This allows integration tests to use the real packages when installed.

Uses patch.dict for automatic cleanup so mocks never leak into other test
directories that may need real langchain imports.
"""

import importlib.util
import sys
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest


def _is_installed(name: str) -> bool:
    """Return True when *name* is genuinely importable.

    Membership in ``sys.modules`` is not a usable proxy: an installed package
    that simply has not been imported yet is absent from ``sys.modules``, and
    mocking over it makes the real package unreachable for the rest of the
    session (this fixture is session-scoped, so its ``patch.dict`` outlives the
    tests in this directory). That is what wedged the ``langchain-integration``
    CI job, whose graph-level tests need the real adapter and ``langchain_core``.
    """
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        # Parent package missing (ModuleNotFoundError) or not a package.
        return False


@pytest.fixture(autouse=True, scope="session")
def _mock_langchain_modules() -> Generator[None, None, None]:
    """Inject sys.modules mocks for any absent langchain packages.

    Only injects mocks for packages that are genuinely missing so that
    integration tests can use the real packages when installed.

    Uses patch.dict for automatic cleanup so mocks never leak into other
    test directories that may need real langchain imports.
    """

    # Create real classes for message types so isinstance() works in tests
    class _AIMessage:
        type = "ai"

        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> dict[str, object]:
            return {"type": self.type, "content": getattr(self, "content", "")}

    class _HumanMessage:
        type = "human"

        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> dict[str, object]:
            return {"type": self.type, "content": getattr(self, "content", "")}

    class _SystemMessage:
        type = "system"

        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> dict[str, object]:
            return {"type": self.type, "content": getattr(self, "content", "")}

    class _ToolMessage:
        type = "tool"

        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> dict[str, object]:
            return {"type": self.type, "content": getattr(self, "content", "")}

    def _messages_from_dict(
        messages: list[dict[str, object]],
    ) -> list[object]:
        """Stub for langchain_core.messages.messages_from_dict."""
        _type_map = {"human": _HumanMessage, "ai": _AIMessage, "tool": _ToolMessage}
        result = []
        for m in messages:
            msg_type = str(m.get("type", "human"))
            data = m.get("data", {})
            cls = _type_map.get(msg_type, _HumanMessage)
            result.append(cls(**(data if isinstance(data, dict) else {})))
        return result

    _lc_messages = MagicMock()
    _lc_messages.AIMessage = _AIMessage
    _lc_messages.HumanMessage = _HumanMessage
    _lc_messages.SystemMessage = _SystemMessage
    _lc_messages.ToolMessage = _ToolMessage
    _lc_messages.messages_from_dict = _messages_from_dict

    mocks: dict[str, MagicMock] = {}

    if not _is_installed("langchain_core"):
        _lc_core = MagicMock()
        _lc_core.messages = _lc_messages
        mocks["langchain_core"] = _lc_core
        mocks["langchain_core.messages"] = _lc_messages
    elif not _is_installed("langchain_core.messages"):
        mocks["langchain_core.messages"] = _lc_messages

    if not _is_installed("langchain_openai"):
        mocks["langchain_openai"] = MagicMock()

    if not _is_installed("langchain_google_genai"):
        mocks["langchain_google_genai"] = MagicMock()

    if not _is_installed("langchain_anthropic"):
        mocks["langchain_anthropic"] = MagicMock()

    if not _is_installed("langchain_ollama"):
        mocks["langchain_ollama"] = MagicMock()

    if not _is_installed("ollama"):
        mocks["ollama"] = MagicMock()

    if not _is_installed("langchain_mcp_adapters"):
        mocks["langchain_mcp_adapters"] = MagicMock()
        mocks["langchain_mcp_adapters.client"] = MagicMock()
        mocks["langchain_mcp_adapters.tools"] = MagicMock()

    if not _is_installed("langgraph"):
        mocks["langgraph"] = MagicMock()
        mocks["langgraph.prebuilt"] = MagicMock()

    if not _is_installed("google.genai"):
        if not _is_installed("google"):
            mocks["google"] = MagicMock()
        mocks["google.genai"] = MagicMock()

    if not _is_installed("httpx"):
        mocks["httpx"] = MagicMock()

    if not mocks:
        yield
        return

    with patch.dict(sys.modules, mocks):
        yield
