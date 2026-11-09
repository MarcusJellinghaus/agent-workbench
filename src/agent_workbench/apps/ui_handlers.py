"""Chainlit handlers of the chat page.

Only this module (and ``ui_launcher._run_chainlit``) imports Chainlit. The origin
middleware is added at import: ``run_chainlit`` loads the target before serving, and
middleware cannot be added once the app has started.
"""

import chainlit as cl
from chainlit.server import app

from agent_workbench.apps.agent import get_runtime, run_turn
from agent_workbench.apps.origin_check import OriginCheckMiddleware, local_origins
from agent_workbench.apps.ui_launcher import chainlit_port
from agent_workbench.core.types import TokenUsage

app.add_middleware(
    OriginCheckMiddleware, allowed_origins=local_origins(chainlit_port())
)


@cl.on_message  # type: ignore[untyped-decorator]  # chainlit is follow_imports=skip
async def on_message(message: cl.Message | None) -> None:
    """Run one agent turn for *message* and stream the answer into the page.

    Stop cancels this task: Chainlit posts its own notice, so nothing is caught here.
    """
    if message is None:  # edit_message is off in config.toml; never fail on it
        return
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
        cl.context.session.thread_id,
        answer.stream_token,
        usage,
    )
    if error:
        if answer.content:
            await answer.send()
        await cl.Message(content=error).send()
        return
    if usage.has_data:
        await answer.stream_token(f"\n\n{usage.display_text()}")
    await answer.send()
