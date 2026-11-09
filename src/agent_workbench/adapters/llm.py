"""Public chat-model, error-mapping, invoke and usage functions over the copied model layer.

The copies are imported inside the function bodies so that importing this module
stays light (no ``langchain_core`` at import time).
"""

from typing import Any, NoReturn

from agent_workbench.adapters.llm_types import UsageInfo
from agent_workbench.core.config import LLMConfig


def create_chat_model(config: LLMConfig, timeout: int) -> Any:
    """Return a configured chat model for *config*.

    A config that violates the per-backend contract (including an unset
    backend) raises ``ValueError``.

    Args:
        config: The LLM configuration.
        timeout: Request timeout in seconds.

    Returns:
        A ``BaseChatModel`` (``Any`` to mypy: ``langchain_core`` is skipped).
    """
    from .langchain._setup import _create_chat_model

    return _create_chat_model(config.as_dict(), timeout=timeout)


def map_provider_error(exc: Exception, config: LLMConfig, chat_model: Any) -> NoReturn:
    """Raise the mapped error for an exception from a chat-model call.

    Provider auth / connection failures become ``LLMAuthError`` /
    ``LLMConnectionError``; anything else unmatched is re-raised unchanged.

    Args:
        exc: The exception raised by the chat model call.
        config: The LLM configuration the model was built from.
        chat_model: The chat model that raised *exc*.

    Raises:
        ValueError: A 404 / model-not-found, with the 404 hint as message.
    """
    from .langchain._config_diagnostics import dialed_url
    from .langchain._errors_404 import _format_404_hint, _is_404_error
    from .langchain._setup import _handle_provider_error

    _handle_provider_error(exc, config.backend, dialed_url(chat_model))
    if _is_404_error(exc):
        raise ValueError(_format_404_hint(config.as_dict())) from exc
    raise exc


def invoke(chat_model: Any, config: LLMConfig, text: str) -> str:
    """Send one prompt and return the answer text.

    Args:
        chat_model: A chat model from :func:`create_chat_model`.
        config: The LLM configuration the model was built from.
        text: The prompt text.

    Returns:
        The answer text.
    """
    try:
        msg = chat_model.invoke(text)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        map_provider_error(exc, config, chat_model)
    return msg.content if isinstance(msg.content, str) else str(msg.content)


def add_usage(total: UsageInfo, message: Any) -> UsageInfo:
    """Return *total* plus the usage carried by *message* (an AIMessage).

    Args:
        total: The usage summed so far.
        message: An ``AIMessage`` / ``AIMessageChunk`` (or any object with an
            optional ``usage_metadata`` attribute).

    Returns:
        *total* itself when *message* carries no usage, else a new ``UsageInfo``
        with all four fields.
    """
    from .langchain._usage import _extract_usage, _sum_usage

    usage = _extract_usage(message)
    if not usage:
        return total
    return _sum_usage(total, usage)
