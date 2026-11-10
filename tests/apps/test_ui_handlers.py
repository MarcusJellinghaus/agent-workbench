"""Chainlit handler module: middleware, data layer, auth, resume, shutdown, messages."""

import asyncio
import getpass
import importlib
import logging
import sys
from collections.abc import Iterator
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import chainlit.data
import pytest
from chainlit.server import app
from chainlit.user import User
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_workbench import apps
from agent_workbench.apps import agent, ui_handlers
from agent_workbench.apps.origin_check import OriginCheckMiddleware, local_origins
from agent_workbench.apps.ui_data_layer import SessionDataLayer
from agent_workbench.apps.ui_launcher import chainlit_port
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.types import TokenUsage
from tests.langchain_doubles import make_scripted_chat_model

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


@pytest.fixture
def finish_turn() -> AsyncMock:
    """Install a mock ``SessionDataLayer`` as Chainlit's; return its ``finish_turn``."""
    finish = AsyncMock()
    layer = MagicMock(spec=SessionDataLayer)
    layer.finish_turn = finish
    chainlit.data._data_layer = layer
    return finish


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


def test_header_auth_returns_the_os_user() -> None:
    user = asyncio.run(ui_handlers.header_auth({}))
    assert isinstance(user, User)
    assert user.identifier == getpass.getuser()


async def test_data_layer_on_the_sessions_folder(tmp_path: Path) -> None:
    db = tmp_path / "sessions" / "chainlit.sqlite"
    with patch("agent_workbench.adapters.config.app_data_dir", return_value=tmp_path):
        layer = ui_handlers.data_layer()
    try:
        assert isinstance(layer, SessionDataLayer)
        assert layer.engine.url.database == str(db)
        assert db.exists()
    finally:
        await layer.close()


def test_checkpointer_is_the_runtimes(runtime: MagicMock) -> None:
    assert asyncio.run(ui_handlers._checkpointer()) is runtime.checkpointer


@pytest.mark.parametrize("state", [None, MagicMock()], ids=["missing", "present"])
def test_resume_warns_without_checkpoint(
    runtime: MagicMock, state: Any, caplog: pytest.LogCaptureFixture
) -> None:
    runtime.checkpointer.aget_tuple = AsyncMock(return_value=state)
    with caplog.at_level(logging.WARNING, logger=ui_handlers.__name__):
        asyncio.run(ui_handlers.on_chat_resume({"id": THREAD_ID}))
    runtime.checkpointer.aget_tuple.assert_awaited_once_with(
        {"configurable": {"thread_id": THREAD_ID}}
    )
    assert (THREAD_ID in caplog.text) is (state is None)


def test_resume_logs_runtime_failure(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch.object(
            ui_handlers, "get_runtime", AsyncMock(side_effect=RuntimeError("no rt"))
        ),
        caplog.at_level(logging.ERROR, logger=ui_handlers.__name__),
    ):
        asyncio.run(ui_handlers.on_chat_resume({"id": THREAD_ID}))
    assert "no rt" in caplog.text


def test_shutdown_closes_runtime() -> None:
    with patch.object(ui_handlers, "close_runtime", AsyncMock()) as close:
        asyncio.run(ui_handlers.on_app_shutdown())
    close.assert_awaited_once_with()


@pytest.mark.usefixtures("runtime", "fake_cl")
@pytest.mark.parametrize(
    ("turn", "raises"),
    [
        ({"return_value": None}, nullcontext()),
        ({"return_value": "Error: boom"}, nullcontext()),
        (
            {"side_effect": asyncio.CancelledError},
            pytest.raises(asyncio.CancelledError),
        ),
    ],
    ids=["answer", "error", "stop"],
)
def test_turn_end_calls_finish_turn(
    turn: dict[str, Any], raises: AbstractContextManager[Any], finish_turn: AsyncMock
) -> None:
    with patch.object(ui_handlers, "run_turn", AsyncMock(**turn)), raises:
        asyncio.run(ui_handlers.on_message(_user_message()))
    finish_turn.assert_awaited_once_with(THREAD_ID)


@pytest.mark.usefixtures("runtime", "fake_cl")
def test_failing_finish_turn_keeps_stop(
    finish_turn: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    finish_turn.side_effect = RuntimeError("boom")
    with (
        patch.object(
            ui_handlers, "run_turn", AsyncMock(side_effect=asyncio.CancelledError)
        ),
        caplog.at_level(logging.ERROR, logger=ui_handlers.__name__),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(ui_handlers.on_message(_user_message()))
    assert any(
        record.exc_info and record.exc_info[0] is RuntimeError
        for record in caplog.records
    )


def test_failing_data_layer_factory_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        patch.object(
            ui_handlers, "get_data_layer", side_effect=RuntimeError("no layer")
        ),
        caplog.at_level(logging.ERROR, logger=ui_handlers.__name__),
    ):
        asyncio.run(ui_handlers._finish_turn(THREAD_ID))
    assert "no layer" in caplog.text


@pytest.mark.parametrize("stop", [False, True], ids=["answer", "stop"])
async def test_turn_on_a_deleted_thread_leaves_no_checkpoints(
    stop: bool,
    fake_cl: FakeChainlit,
    runtime: MagicMock,
    data_layer: SessionDataLayer,
    checkpointer: AsyncSqliteSaver,
) -> None:
    model = make_scripted_chat_model(lambda _n: AIMessage(content="hi"), "fake")
    runtime.graph = agent.build_graph(model, [], checkpointer)
    runtime.chat_model = model
    runtime.llm_config = LLMConfig(backend="openai", model="gpt-4o")
    user = await data_layer.create_user(User(identifier="alice"))
    assert user is not None
    await data_layer.update_thread(THREAD_ID, name="Chat", user_id=user.id)
    await data_layer.delete_thread(THREAD_ID)

    if stop:
        # Stop while the answer is shown: the graph has written its checkpoints.
        answering = asyncio.Event()

        async def hang(_text: str) -> None:
            answering.set()
            await asyncio.Event().wait()

        make_message = fake_cl.cl.Message.side_effect

        def hanging_message(content: str = "") -> MagicMock:
            msg: MagicMock = make_message(content)
            msg.stream_token = AsyncMock(side_effect=hang)
            return msg

        fake_cl.cl.Message.side_effect = hanging_message
        task = asyncio.create_task(ui_handlers.on_message(_user_message()))
        await answering.wait()
        assert await checkpointer.aget_tuple(_config(THREAD_ID)) is not None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await ui_handlers.on_message(_user_message())
        (answer,) = fake_cl.messages
        answer.stream_token.assert_awaited_once_with("hi")

    assert await checkpointer.aget_tuple(_config(THREAD_ID)) is None


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}
