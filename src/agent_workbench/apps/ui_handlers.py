"""Chainlit handlers of the chat page.

Chainlit is imported here, in ``ui_data_layer`` (imported only by this module) and in
``ui_launcher._run_chainlit``. The origin middleware is added at import:
``run_chainlit`` loads the target before serving, and middleware cannot be added once
the app has started.
"""

import getpass
import logging
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
from agent_workbench.core.types import TokenUsage
from agent_workbench.services.tool_call_log import truncate_text

logger = logging.getLogger(__name__)

TOOL_OUTPUT_CHARS = 2000  # characters of a tool result shown in its step

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
    """Warn when the checkpointer has no state for the resumed *thread*.

    The page then shows the conversation the model no longer knows; the user can
    still continue it. Logs, never raises: Chainlit awaits this before it sends the
    thread to the page.
    """
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
