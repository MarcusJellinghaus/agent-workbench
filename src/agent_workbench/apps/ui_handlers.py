"""Chainlit handlers of the chat page.

Chainlit is imported here, in ``ui_data_layer`` (imported only by this module) and in
``ui_launcher._run_chainlit``. The origin middleware is added at import:
``run_chainlit`` loads the target before serving, and middleware cannot be added once
the app has started.
"""

import asyncio
import getpass
import json
import logging
import re
from typing import Any

import chainlit as cl
from chainlit.data import get_data_layer
from chainlit.server import app
from chainlit.utils import utc_now

from agent_workbench.apps.agent import (
    close_runtime,
    get_runtime,
    run_turn,
    sessions_dir,
)
from agent_workbench.apps.origin_check import OriginCheckMiddleware, local_origins
from agent_workbench.apps.ui_data_layer import SessionDataLayer
from agent_workbench.apps.ui_launcher import chainlit_port
from agent_workbench.core.permissions import PermissionMode
from agent_workbench.core.types import TokenUsage
from agent_workbench.services.tool_call_log import truncate_text

logger = logging.getLogger(__name__)

TOOL_OUTPUT_CHARS = 2000  # characters of a tool result shown in its step
DIALOG_TIMEOUT = 300  # seconds; a timeout counts as Cancel
GRANTS_KEY = "permission_grants"  # cl.user_session key of the ask_session grants

app.add_middleware(
    OriginCheckMiddleware, allowed_origins=local_origins(chainlit_port())
)


class ToolSteps:
    """The open ``cl.Step(type="tool")`` objects of one turn, by run id.

    The data layer persists the steps in ``chainlit.sqlite``.
    """

    def __init__(self) -> None:
        self._open: dict[str, cl.Step] = {}

    async def start(self, run_id: str, name: str, args: dict[str, Any]) -> None:
        """Open and send a tool step showing *args*."""
        step = cl.Step(name=name, type="tool")
        step.input = args
        step.start = utc_now()
        await step.send()
        self._open[run_id] = step

    async def end(self, run_id: str, output: str) -> None:
        """Set the truncated *output* and close the step (unknown run id: no-op)."""
        step = self._open.pop(run_id, None)
        if step is None:
            return
        step.output = truncate_text(output, TOOL_OUTPUT_CHARS)
        step.end = utc_now()
        await step.update()

    async def close_all(self) -> None:
        """Close every step still open; logs, never raises.

        A failed or stopped tool may emit no end event.
        """
        for run_id in list(self._open):
            try:
                await self.end(run_id, "")
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Closing the tool step of run %s failed", run_id)


def arguments_markdown(name: str, args: dict[str, Any]) -> str:
    """Return the tool name plus *args* as JSON in a code fence no backtick run can close.

    Args:
        name: The tool name.
        args: The call's arguments; values JSON cannot encode are shown as ``str``.

    Returns:
        Markdown whose fence is longer than the longest backtick run of the JSON.
    """
    text = json.dumps(args, indent=2, ensure_ascii=False, default=str)
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"Tool call **{name}** with these arguments:\n\n{fence}json\n{text}\n{fence}"


async def confirm_tool_call(
    name: str, args: dict[str, Any], mode: PermissionMode
) -> bool:
    """Show the call's arguments, then ask OK / Cancel; True only for OK.

    The arguments message stays visible and is stored with the thread. A timeout
    counts as Cancel. Stop during the dialog removes the buttons before it propagates.

    Args:
        name: The tool name.
        args: The call's arguments.
        mode: ``ask`` or ``ask_session``; the text says what OK means.

    Returns:
        True when the user chose OK.

    Raises:
        asyncio.CancelledError: The turn was stopped during the dialog.
    """
    await cl.Message(content=arguments_markdown(name, args)).send()
    text = f"Allow **{name}**?"
    if mode == "ask_session":
        text += " OK allows this tool for the rest of the conversation."
    ask = cl.AskActionMessage(
        content=text,
        actions=[
            cl.Action(name="ok", payload={}, label="OK"),
            cl.Action(name="cancel", payload={}, label="Cancel"),
        ],
        timeout=DIALOG_TIMEOUT,
    )
    try:
        res = await ask.send()
    except asyncio.CancelledError:
        await _cancel_ask(ask)
        raise
    return res is not None and res.get("name") == "ok"


async def _cancel_ask(ask: cl.AskActionMessage) -> None:
    """Remove the buttons, clear the ask, mark its text cancelled; logs, never raises.

    Chainlit's ``send_ask_user`` skips this cleanup when the waiting task is cancelled.
    """
    try:
        for action in ask.actions:
            await action.remove()
        await cl.context.emitter.clear("clear_ask")
        ask.content = "Cancelled – the tool call did not run."
        ask.wait_for_answer = False
        await ask.update()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Cleaning up the cancelled approval prompt failed")


def _session_grants() -> set[str]:
    """Return the conversation's ``ask_session`` grants, created if missing.

    A new chat or a page reload gets a new user session, hence a new set; a restored
    non-set value (e.g. ``null``) is replaced.
    """
    grants = cl.user_session.get(GRANTS_KEY)
    if not isinstance(grants, set):
        grants = set()
        cl.user_session.set(GRANTS_KEY, grants)
    return grants


@cl.data_layer  # type: ignore[untyped-decorator]  # chainlit is follow_imports=skip
def data_layer() -> SessionDataLayer:
    """Build Chainlit's data layer; Chainlit calls this once, on first use.

    Returns:
        The data layer on ``<app-data>/sessions/chainlit.sqlite``.
    """
    return SessionDataLayer(sessions_dir() / "chainlit.sqlite", _checkpointer)


@cl.header_auth_callback  # type: ignore[untyped-decorator]  # chainlit is follow_imports=skip
async def header_auth(headers: Any) -> cl.User:  # pylint: disable=unused-argument
    """Sign in every request as the OS user: the page is reachable from localhost only.

    Returns:
        A user whose identifier is the OS user name.
    """
    return cl.User(identifier=getpass.getuser())


@cl.on_chat_resume  # type: ignore[untyped-decorator]  # chainlit is follow_imports=skip
async def on_chat_resume(thread: dict[str, Any]) -> None:
    """Reset the ``ask_session`` grants; warn when the checkpointer has no state.

    A resumed conversation asks again. Without a checkpoint for *thread* the page
    shows the conversation the model no longer knows; the user can still continue
    it. Logs, never raises: Chainlit awaits this before it sends the thread to the
    page.
    """
    cl.user_session.set(GRANTS_KEY, set())
    try:
        runtime = await get_runtime()
        state = await runtime.checkpointer.aget_tuple(
            {"configurable": {"thread_id": thread["id"]}}
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Checking the checkpoint of thread %s failed", thread["id"])
        return
    if state is None:
        logger.warning("No checkpoint for resumed thread %s", thread["id"])


@cl.on_app_shutdown  # type: ignore[untyped-decorator]  # chainlit is follow_imports=skip
async def on_app_shutdown() -> None:
    """Close the checkpointer's connection."""
    await close_runtime()


@cl.on_message  # type: ignore[untyped-decorator]  # chainlit is follow_imports=skip
async def on_message(message: cl.Message | None) -> None:
    """Run one agent turn for *message* and stream the answer into the page.

    Stop cancels this task: Chainlit posts its own notice, so nothing is caught here.
    Each tool call shows as a step. However the turn ends, the steps still open are
    closed and a thread deleted meanwhile is deleted again.
    """
    if message is None:  # edit_message is off in config.toml; never fail on it
        return
    thread_id = cl.context.session.thread_id
    steps = ToolSteps()
    try:
        runtime = await get_runtime()
        # One TokenUsage per chat: "New chat" starts a new user session.
        usage = cl.user_session.get("token_usage") or TokenUsage()
        cl.user_session.set("token_usage", usage)
        answer = cl.Message(content="")
        error = await run_turn(
            runtime.graph,
            runtime.chat_model,
            runtime.llm_config,
            message.content,
            thread_id,
            answer.stream_token,
            usage,
            on_tool_start=steps.start,
            on_tool_end=steps.end,
            confirm=confirm_tool_call,
            grants=_session_grants(),
        )
        if error:
            if answer.content:
                await answer.send()
            await cl.Message(content=error).send()
            return
        if usage.has_data:
            await answer.stream_token(f"\n\n{usage.display_text()}")
        await answer.send()
    finally:
        await steps.close_all()
        await _finish_turn(thread_id)


async def _checkpointer() -> Any:
    """Return the runtime's checkpointer (the data layer's ``CheckpointerProvider``)."""
    return (await get_runtime()).checkpointer


async def _finish_turn(thread_id: str) -> None:
    """Let the data layer delete again what the turn wrote to a deleted thread.

    Logs, never raises: runs in ``on_message``'s ``finally`` and must not replace a
    ``CancelledError`` from Stop or the turn's own error.
    """
    try:
        # From chainlit.data, not cl: the handler tests replace this module's cl.
        layer = get_data_layer()
        if not isinstance(layer, SessionDataLayer):
            return
        await layer.finish_turn(thread_id)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Deleting the turn of deleted thread %s failed", thread_id)
