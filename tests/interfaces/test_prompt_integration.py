"""Real-provider ``prompt`` test; runs only on request (``-m integration``)."""

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from agent_workbench.adapters.config import load_llm_config
from agent_workbench.interfaces.cli import main

pytestmark = pytest.mark.integration

_VENDOR_KEY_ENV: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


@pytest.fixture(autouse=True)
def _patch_startup() -> Iterator[None]:
    with (
        patch("agent_workbench.interfaces.cli.setup_logging"),
        patch("agent_workbench.adapters.ssl_setup.ensure_truststore"),
    ):
        yield


def test_prompt_real_provider(capsys: pytest.CaptureFixture[str]) -> None:
    config = load_llm_config()
    if config.backend is None:
        pytest.skip("no LLM backend configured")
    has_key = bool(config.api_key) or any(
        os.environ.get(var) for var in _VENDOR_KEY_ENV.get(config.backend, ())
    )
    if config.backend != "ollama" and not has_key:
        pytest.skip(f"no API key for backend {config.backend}")
    assert main(["prompt", "Reply with OK"]) == 0
    assert capsys.readouterr().out.strip()
