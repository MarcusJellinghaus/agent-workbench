from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent_workbench.adapters import llm
from agent_workbench.adapters.langchain._errors_404 import _format_404_hint
from agent_workbench.adapters.langchain._exceptions import LLMConnectionError
from agent_workbench.adapters.llm_types import UsageInfo
from agent_workbench.core.config import LLMConfig

_CONFIG = LLMConfig(backend="ollama", model="llama3")


def test_create_chat_model_forwards_config_and_timeout() -> None:
    sentinel = object()
    with patch(
        "agent_workbench.adapters.langchain._setup._create_chat_model",
        return_value=sentinel,
    ) as create:
        result = llm.create_chat_model(_CONFIG, timeout=12)
    assert result is sentinel
    create.assert_called_once_with(_CONFIG.as_dict(), timeout=12)


def test_create_chat_model_unset_backend_raises() -> None:
    with pytest.raises(ValueError):
        llm.create_chat_model(LLMConfig(), timeout=5)


def test_invoke_returns_str_content() -> None:
    chat_model = MagicMock()
    chat_model.invoke.return_value.content = "hello"
    assert llm.invoke(chat_model, _CONFIG, "hi") == "hello"
    chat_model.invoke.assert_called_once_with("hi")


def test_invoke_stringifies_non_str_content() -> None:
    content = [{"type": "text", "text": "hello"}]
    chat_model = MagicMock()
    chat_model.invoke.return_value.content = content
    assert llm.invoke(chat_model, _CONFIG, "hi") == str(content)


def test_invoke_connection_error_mapped() -> None:
    chat_model = MagicMock()
    chat_model.invoke.side_effect = ConnectionError("refused")
    with pytest.raises(LLMConnectionError):
        llm.invoke(chat_model, _CONFIG, "hi")


def test_invoke_404_raises_value_error_with_hint() -> None:
    chat_model = MagicMock()
    error = Exception("404 model not found")
    chat_model.invoke.side_effect = error
    with patch(
        "agent_workbench.adapters.langchain._errors_404._get_model_suggestions",
        return_value="",
    ):
        with pytest.raises(ValueError) as exc_info:
            llm.invoke(chat_model, _CONFIG, "hi")
        expected = _format_404_hint(_CONFIG.as_dict())
    assert str(exc_info.value) == expected
    assert exc_info.value.__cause__ is error


def test_invoke_unmatched_error_reraised_unchanged() -> None:
    chat_model = MagicMock()
    error = RuntimeError("boom")
    chat_model.invoke.side_effect = error
    with pytest.raises(RuntimeError) as exc_info:
        llm.invoke(chat_model, _CONFIG, "hi")
    assert exc_info.value is error


def test_add_usage_without_usage_metadata_returns_total_unchanged() -> None:
    total: UsageInfo = {}
    assert llm.add_usage(total, SimpleNamespace()) is total
    assert llm.add_usage(total, SimpleNamespace(usage_metadata=None)) is total
    assert not total


def test_add_usage_sums_two_messages() -> None:
    first = SimpleNamespace(
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 3,
            "input_token_details": {"cache_read": 4},
        }
    )
    second = SimpleNamespace(
        usage_metadata={
            "input_tokens": 20,
            "output_tokens": 5,
            "input_token_details": {"cache_read": 6, "cache_creation": 2},
        }
    )
    total = llm.add_usage(llm.add_usage({}, first), second)
    assert total == {
        "input_tokens": 30,
        "output_tokens": 8,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 2,
    }
