"""``create_chat_model`` keeps langchain_openai's own ``stream_usage`` default."""

from typing import Any
from unittest.mock import patch

import pytest
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from agent_workbench.adapters import llm
from agent_workbench.core.config import LLMConfig

_CLEARED_ENV = (
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "OPENAI_PROXY",
    "AZURE_OPENAI_ENDPOINT",
    "LANGSMITH_GATEWAY",
    "LANGSMITH_GATEWAY_API_KEY",
    "LANGSMITH_API_KEY",
)


@pytest.fixture(autouse=True)
def _openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CLEARED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-test")


def test_openai_default_url_enables_stream_usage() -> None:
    config = LLMConfig(backend="openai", model="gpt-4o")
    model = llm.create_chat_model(config, timeout=5)
    reference = ChatOpenAI(model="gpt-4o", timeout=5)
    assert model.stream_usage is True
    assert model.stream_usage == reference.stream_usage


def test_openai_custom_base_url_keeps_langchain_value() -> None:
    url = "http://localhost:1234/v1"
    config = LLMConfig(backend="openai", model="local", base_url=url)
    model = llm.create_chat_model(config, timeout=5)
    reference = ChatOpenAI(model="local", base_url=url, timeout=5)
    assert model.stream_usage is None
    assert model.stream_usage == reference.stream_usage


def test_azure_keeps_langchain_default() -> None:
    endpoint = "https://example.openai.azure.com/"
    config = LLMConfig(
        backend="openai",
        model="deployment",
        base_url=endpoint,
        api_version="2024-02-01",
    )
    model = llm.create_chat_model(config, timeout=5)
    reference = AzureChatOpenAI(
        azure_deployment="deployment",
        azure_endpoint=endpoint,
        api_version="2024-02-01",
        timeout=5,
    )
    assert isinstance(model, AzureChatOpenAI)
    assert model.stream_usage is True
    assert model.stream_usage == reference.stream_usage


def test_non_openai_backend_not_mirrored() -> None:
    sentinel: Any = object()
    config = LLMConfig(backend="ollama", model="llama3")
    with (
        patch(
            "agent_workbench.adapters.langchain._setup._create_chat_model",
            return_value=sentinel,
        ),
        patch.object(llm, "_mirror_openai_stream_usage") as mirror,
    ):
        assert llm.create_chat_model(config, timeout=5) is sentinel
    mirror.assert_not_called()
