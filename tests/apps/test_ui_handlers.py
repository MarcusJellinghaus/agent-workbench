"""Chainlit handler module: origin middleware and ``on_message``."""

import asyncio
import importlib
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chainlit.server import app

from agent_workbench import apps
from agent_workbench.apps import ui_handlers
from agent_workbench.apps.origin_check import OriginCheckMiddleware, local_origins
from agent_workbench.apps.ui_launcher import chainlit_port
from agent_workbench.core.types import TokenUsage

THREAD_ID = "thread-1"


@dataclass
class FakeChainlit:
    """Stand-in for the ``chainlit`` module as ``on_message`` uses it."""

    cl: MagicMock
    messages: list[MagicMock] = field(default_factory=list)
    session: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def fake_cl() -> Iterator[FakeChainlit]:
    """Patch ``ui_handlers.cl``: messages record calls, ``user_session`` is a dict."""
    cl = MagicMock()
    fake = FakeChainlit(cl=cl)

    def message(content: str = "") -> MagicMock:
        msg = MagicMock(content=content)
        msg.stream_token = AsyncMock()
        msg.send = AsyncMock()
        fake.messages.append(msg)
        return msg

    cl.Message.side_effect = message
    cl.user_session.get.side_effect = fake.session.get
    cl.user_session.set.side_effect = fake.session.__setitem__
    cl.context.session.thread_id = THREAD_ID
    with patch.object(ui_handlers, "cl", cl):
        yield fake


@pytest.fixture
def runtime() -> Iterator[MagicMock]:
    """Patch ``get_runtime`` with a runtime of mocks."""
    rt = MagicMock()
    with patch.object(ui_handlers, "get_runtime", AsyncMock(return_value=rt)):
        yield rt


def _user_message(text: str = "hi") -> MagicMock:
    return MagicMock(content=text)


def test_import_adds_origin_middleware() -> None:
    entries = [m for m in app.user_middleware if m.cls is OriginCheckMiddleware]
    assert len(entries) == 1
    assert entries[0].kwargs == {"allowed_origins": local_origins(chainlit_port())}


@pytest.mark.usefixtures("runtime")
def test_success_streams_usage_and_sends_answer(fake_cl: FakeChainlit) -> None:
    async def run_turn(*args: Any) -> None:
        on_text, usage = args[5], args[6]
        await on_text("Hello")
        usage.update(10, 5)

    with patch.object(ui_handlers, "run_turn", side_effect=run_turn) as turn:
        asyncio.run(ui_handlers.on_message(_user_message("question")))

    args = turn.call_args.args
    assert args[3] == "question"
    assert args[4] == THREAD_ID
    usage = fake_cl.session["token_usage"]
    assert args[6] is usage
    (answer,) = fake_cl.messages
    assert answer.stream_token.await_args_list[0].args == ("Hello",)
    assert answer.stream_token.await_args_list[-1].args == (
        f"\n\n{usage.display_text()}",
    )
    answer.send.assert_awaited_once()


@pytest.mark.usefixtures("runtime")
def test_no_usage_line_without_data(fake_cl: FakeChainlit) -> None:
    with patch.object(ui_handlers, "run_turn", AsyncMock(return_value=None)):
        asyncio.run(ui_handlers.on_message(_user_message()))
    (answer,) = fake_cl.messages
    answer.stream_token.assert_not_awaited()
    answer.send.assert_awaited_once()


@pytest.mark.usefixtures("runtime")
def test_error_sends_error_message(fake_cl: FakeChainlit) -> None:
    with patch.object(ui_handlers, "run_turn", AsyncMock(return_value="Error: boom")):
        asyncio.run(ui_handlers.on_message(_user_message()))
    answer, error = fake_cl.messages
    assert error.content == "Error: boom"
    error.send.assert_awaited_once()
    answer.stream_token.assert_not_awaited()


@pytest.mark.usefixtures("runtime")
def test_none_message_is_ignored(fake_cl: FakeChainlit) -> None:
    with patch.object(ui_handlers, "run_turn", AsyncMock()) as turn:
        asyncio.run(ui_handlers.on_message(None))
    turn.assert_not_called()
    assert not fake_cl.messages


@pytest.mark.usefixtures("runtime")
def test_session_reuses_token_usage(fake_cl: FakeChainlit) -> None:
    with patch.object(ui_handlers, "run_turn", AsyncMock(return_value=None)) as turn:
        asyncio.run(ui_handlers.on_message(_user_message("one")))
        asyncio.run(ui_handlers.on_message(_user_message("two")))
    first, second = (call.args[6] for call in turn.call_args_list)
    assert isinstance(first, TokenUsage)
    assert first is second is fake_cl.session["token_usage"]


@pytest.mark.usefixtures("runtime")
def test_stop_propagates_without_messages(fake_cl: FakeChainlit) -> None:
    with (
        patch.object(
            ui_handlers, "run_turn", AsyncMock(side_effect=asyncio.CancelledError)
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(ui_handlers.on_message(_user_message()))
    for msg in fake_cl.messages:
        msg.send.assert_not_awaited()
        msg.stream_token.assert_not_awaited()


def test_target_imports_handlers() -> None:
    # Fresh imports of both modules; the middleware must not be added twice to the app.
    with (
        patch.dict(sys.modules),
        patch.object(apps, "ui_handlers", ui_handlers),
        patch.object(app, "add_middleware") as add_middleware,
    ):
        sys.modules.pop("agent_workbench.apps.ui_target", None)
        sys.modules.pop("agent_workbench.apps.ui_handlers")
        importlib.import_module("agent_workbench.apps.ui_target")
        assert "agent_workbench.apps.ui_handlers" in sys.modules
    add_middleware.assert_called_once()
