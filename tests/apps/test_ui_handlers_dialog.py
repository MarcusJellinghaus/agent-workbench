"""Approval dialog of ``ui_handlers``: arguments message, OK / Cancel, Stop cleanup."""

import asyncio
import json
import re
from collections.abc import Awaitable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Not chainlit.context.context_var: chainlit's __init__ shadows the module with its
# context proxy.
from chainlit.context import ChainlitContext, context_var
from chainlit.emitter import BaseChainlitEmitter
from chainlit.session import HTTPSession
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from mcp_coder_utils.tool_spec import tool_spec

from agent_workbench.adapters.tools import to_structured_tool
from agent_workbench.apps import agent, ui_handlers
from agent_workbench.core.config import LLMConfig
from agent_workbench.core.permissions import PermissionMode
from agent_workbench.core.types import TokenUsage
from tests.langchain_doubles import make_scripted_chat_model

ARGS = {"path": "a.txt", "text": "hello"}


@dataclass
class FakeDialogChainlit:
    """Stand-in for ``chainlit`` as ``confirm_tool_call`` uses it."""

    cl: MagicMock
    events: list[str] = field(default_factory=list)
    messages: list[MagicMock] = field(default_factory=list)
    asks: list[MagicMock] = field(default_factory=list)
    answer: dict[str, Any] | None = None


@pytest.fixture
def fake_cl() -> Iterator[FakeDialogChainlit]:
    """Patch ``ui_handlers.cl``: messages and asks record their sends in order."""
    cl = MagicMock()
    fake = FakeDialogChainlit(cl=cl)

    def message(content: str = "") -> MagicMock:
        msg = MagicMock(content=content)
        msg.send = AsyncMock(side_effect=lambda: fake.events.append("message"))
        fake.messages.append(msg)
        return msg

    def ask_message(content: str, actions: list[Any], timeout: int) -> MagicMock:
        ask = MagicMock(content=content, actions=actions, timeout=timeout)

        async def send() -> dict[str, Any] | None:
            fake.events.append("ask")
            return fake.answer

        ask.send = AsyncMock(side_effect=send)
        fake.asks.append(ask)
        return ask

    def action(name: str, payload: dict[str, Any], label: str) -> MagicMock:
        act = MagicMock(payload=payload, label=label)
        act.name = name
        return act

    cl.Message.side_effect = message
    cl.AskActionMessage.side_effect = ask_message
    cl.Action.side_effect = action
    with patch.object(ui_handlers, "cl", cl):
        yield fake


def _fenced_json(content: str) -> tuple[str, str, str]:
    """Split *content* at its JSON code fence: (before, JSON text, after)."""
    match = re.search(r"(`{3,})json\n", content)
    assert match is not None
    fence = match.group(1)
    body_start = match.end()
    closing = content.index(f"\n{fence}", body_start)
    after = content[closing + 1 + len(fence) :]
    return content[: match.start()], content[body_start:closing], after


# --- arguments message ------------------------------------------------------------


async def test_arguments_message_is_sent_before_the_ask(
    fake_cl: FakeDialogChainlit,
) -> None:
    fake_cl.answer = {"name": "ok", "label": "OK"}

    await ui_handlers.confirm_tool_call("write_file", ARGS, "ask")

    assert fake_cl.events == ["message", "ask"]
    (message,) = fake_cl.messages
    before, text, after = _fenced_json(message.content)
    assert "write_file" in before
    assert json.loads(text) == ARGS
    assert after == ""


@pytest.mark.parametrize(
    "value",
    ["```", "x ```` y", "`" * 7 + " end", "```json\n}\n```"],
    ids=["three", "four", "seven", "fence-like"],
)
def test_backtick_runs_stay_inside_the_fence(value: str) -> None:
    content = ui_handlers.arguments_markdown("tool", {"text": value})

    fence = re.search(r"(`{3,})json\n", content)
    assert fence is not None
    longest = max(len(run) for run in re.findall(r"`+", json.dumps(value)))
    assert len(fence.group(1)) > longest
    _before, text, after = _fenced_json(content)
    assert json.loads(text) == {"text": value}
    assert after == ""


def test_arguments_markdown_keeps_non_ascii_and_odd_values() -> None:
    content = ui_handlers.arguments_markdown("tool", {"name": "Grüße", "p": Path("x")})
    assert "Grüße" in content
    _before, text, _after = _fenced_json(content)
    assert json.loads(text) == {"name": "Grüße", "p": str(Path("x"))}


# --- ask text, timeout, answers -----------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "session_note"), [("ask", False), ("ask_session", True)]
)
async def test_ask_text_names_the_tool_and_the_session_grant(
    mode: PermissionMode, session_note: bool, fake_cl: FakeDialogChainlit
) -> None:
    await ui_handlers.confirm_tool_call("write_file", ARGS, mode)

    (ask,) = fake_cl.asks
    assert "write_file" in ask.content
    assert ("rest of the conversation" in ask.content) is session_note
    assert ask.timeout == ui_handlers.DIALOG_TIMEOUT == 300
    assert [(a.name, a.label) for a in ask.actions] == [
        ("ok", "OK"),
        ("cancel", "Cancel"),
    ]


@pytest.mark.parametrize(
    ("answer", "approved"),
    [
        ({"name": "ok", "label": "OK"}, True),
        ({"name": "cancel", "label": "Cancel"}, False),
        (None, False),
    ],
    ids=["ok", "cancel", "timeout"],
)
async def test_only_ok_approves(
    answer: dict[str, Any] | None, approved: bool, fake_cl: FakeDialogChainlit
) -> None:
    fake_cl.answer = answer
    assert await ui_handlers.confirm_tool_call("write_file", ARGS, "ask") is approved


# --- Stop during the dialog, with a real Chainlit context ---------------------------


class RecordingEmitter(BaseChainlitEmitter):  # type: ignore[misc]  # chainlit is follow_imports=skip
    """Records ``emit`` / ``clear`` / ``update_step``; ``send_ask_user`` never answers."""

    def __init__(self, session: HTTPSession) -> None:
        super().__init__(session)
        self.emitted: list[tuple[str, Any]] = []
        self.cleared: list[str] = []
        self.updated: list[dict[str, Any]] = []
        self.asked = asyncio.Event()

    async def emit(self, event: str, data: Any) -> None:
        self.emitted.append((event, data))

    def clear(self, event: str) -> Awaitable[None]:
        """Record *event*; awaitable, as ``ChainlitEmitter.clear`` returns ``emit(...)``."""
        self.cleared.append(event)
        return asyncio.sleep(0)

    async def update_step(self, step_dict: Any) -> None:
        self.updated.append(dict(step_dict))

    async def send_ask_user(
        self, step_dict: Any, spec: Any, raise_on_timeout: bool = False
    ) -> Any:
        self.asked.set()
        await asyncio.Event().wait()


def _log_outcomes(tmp_path: Path) -> list[str]:
    path = tmp_path / "logs" / "tool_calls.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["outcome"] for line in lines]


async def test_stop_during_the_dialog_cleans_up_the_ask(tmp_path: Path) -> None:
    ran: list[str] = []

    def guarded(text: str) -> str:
        """Record the run."""
        ran.append(text)
        return text

    tool = to_structured_tool(
        tool_spec(guarded, group="fake.read", read_only=True, name="guarded")
    )

    def script(n: int) -> AIMessage:
        if n == 1:
            call = {"name": "guarded", "args": {"text": "x"}, "id": "call-1"}
            return AIMessage(content="", tool_calls=[call])
        return AIMessage(content="done")

    model = make_scripted_chat_model(script, "fake")
    graph = agent.build_graph(model, [tool], InMemorySaver(), modes={"guarded": "ask"})
    session = HTTPSession(id="session-1", client_type="webapp", thread_id="thread-1")
    emitter = RecordingEmitter(session)
    token = context_var.set(ChainlitContext(session, emitter))
    try:
        task = asyncio.create_task(
            agent.run_turn(
                graph,
                model,
                LLMConfig(backend="openai", model="gpt-4o"),
                "go",
                "thread-1",
                AsyncMock(),
                TokenUsage(),
                confirm=ui_handlers.confirm_tool_call,
                grants=set(),
            )
        )
        await asyncio.wait_for(emitter.asked.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        context_var.reset(token)

    assert not ran
    sent = [data["id"] for event, data in emitter.emitted if event == "action"]
    removed = [
        data["id"] for event, data in emitter.emitted if event == "remove_action"
    ]
    assert len(sent) == 2
    assert removed == sent
    assert emitter.cleared == ["clear_ask"]
    assert "Cancelled" in emitter.updated[-1]["output"]
    assert emitter.updated[-1]["waitForAnswer"] is False
    assert _log_outcomes(tmp_path) == ["cancelled"]


async def test_failing_cleanup_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    ask = MagicMock()
    ask.actions = [MagicMock(remove=AsyncMock(side_effect=RuntimeError("gone")))]
    with caplog.at_level("ERROR", logger=ui_handlers.__name__):
        await ui_handlers._cancel_ask(ask)
    assert "gone" in caplog.text
