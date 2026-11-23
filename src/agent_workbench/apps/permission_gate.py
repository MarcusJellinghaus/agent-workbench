"""Permission gate: the ``ToolNode`` interceptor that applies each tool's mode.

Per call, in this order: a tool that is not bound (``deny`` or unknown) and invalid
arguments are logged and handed to ``ToolNode``, which answers with its error text; an
``allow`` tool runs; an ``ask`` / ``ask_session`` tool runs only after the user's OK in
the turn's confirm callback. Calls that do not run are logged here; calls that run are
logged by ``services.tool_call_log.wrap_spec``.

The per-turn objects arrive in ``configurable[TURN_PERMISSIONS_KEY]``. Without them every
``ask`` / ``ask_session`` call is refused (fail closed). The sync path never runs a tool:
the graph is invoked asynchronously only, so a sync call has no approval prompt.
"""

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, ValidationError

from agent_workbench.core.permissions import PermissionMode
from agent_workbench.services.tool_call_log import elapsed, log_tool_call

logger = logging.getLogger(__name__)

TURN_PERMISSIONS_KEY = "turn_permissions"
DENY_USER = (
    "Tool call denied by the user. Do not retry this call — choose a different "
    "approach, or ask the user what they would prefer."
)
DENY_UNAVAILABLE = (
    "This tool requires approval, but no approval prompt was reachable, so the call "
    "was refused without asking the user. Choose a different approach or ask the user "
    "how to proceed."
)

Confirm = Callable[[str, dict[str, Any], PermissionMode], Awaitable[bool]]
"""Tool name, arguments, mode → True when the user approved the call."""

Execute = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]
SyncExecute = Callable[[ToolCallRequest], ToolMessage | Command]


@dataclass(frozen=True)
class TurnPermissions:
    """Per-turn objects, passed by identity in ``configurable[TURN_PERMISSIONS_KEY]``.

    Attributes:
        confirm: Asks the user to approve one call.
        grants: The ``ask_session`` grants of the conversation (tool names).
        lock: At most one dialog per turn.
    """

    confirm: Confirm
    grants: set[str]
    lock: asyncio.Lock


def deny_message(text: str, request: ToolCallRequest) -> ToolMessage:
    """Return the error ``ToolMessage`` answering *request* with *text*.

    Args:
        text: ``DENY_USER`` or ``DENY_UNAVAILABLE``.
        request: The refused tool call.

    Returns:
        A ``ToolMessage`` with ``status="error"`` and the call's id.
    """
    call = request.tool_call
    return ToolMessage(
        content=text, name=call["name"], tool_call_id=call["id"], status="error"
    )


def _turn_permissions(request: ToolCallRequest) -> TurnPermissions | None:
    """Return the ``TurnPermissions`` of the running turn, or None without them."""
    config = getattr(request.runtime, "config", None) or {}
    turn = (config.get("configurable") or {}).get(TURN_PERMISSIONS_KEY)
    return turn if isinstance(turn, TurnPermissions) else None


def _args_valid(tool: BaseTool, args: dict[str, Any]) -> bool:
    """Return False when *args* fail the tool's pydantic args model."""
    schema = tool.args_schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        try:
            schema.model_validate(args)
        except ValidationError:
            return False
    return True


async def gate_tool_call(
    request: ToolCallRequest,
    execute: Execute,
    modes: Mapping[str, PermissionMode],
) -> ToolMessage | Command:
    """Apply the mode of the requested tool; run it via *execute* only when allowed.

    Args:
        request: The tool call from ``ToolNode``.
        execute: Runs the call (``ToolNode``'s validation, the tool, error handling).
        modes: ``{tool name: mode}`` for every configured tool.

    Returns:
        *execute*'s result, or a denial ``ToolMessage``.

    Raises:
        asyncio.CancelledError: The turn was stopped during the dialog or while
            waiting for it.
    """
    start = time.monotonic()
    call = request.tool_call
    name, args = call["name"], call["args"]
    if request.tool is None:
        # ToolNode answers with its invalid-tool text, naming the bound tools only.
        outcome = "blocked" if name in modes else "unknown_tool"
        log_tool_call(name, args, outcome, None, elapsed(start))
        return await execute(request)
    if not _args_valid(request.tool, args):
        log_tool_call(name, args, "invalid_arguments", None, elapsed(start))
        return await execute(request)
    mode = modes[name]
    if mode == "allow":
        return await execute(request)
    turn = _turn_permissions(request)
    if turn is None:
        log_tool_call(name, args, "denied", None, elapsed(start))
        return deny_message(DENY_UNAVAILABLE, request)
    if not (mode == "ask_session" and name in turn.grants):
        try:
            async with turn.lock:
                # Re-checked under the lock: a call gathered with this one may have
                # been granted while this one waited.
                approved = (mode == "ask_session" and name in turn.grants) or (
                    await turn.confirm(name, args, mode)
                )
                if approved and mode == "ask_session":
                    turn.grants.add(name)
        except asyncio.CancelledError:
            log_tool_call(name, args, "cancelled", None, elapsed(start))
            raise
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("The approval prompt for tool %r failed", name)
            log_tool_call(name, args, "dialog_error", None, elapsed(start))
            return deny_message(DENY_UNAVAILABLE, request)
        if not approved:
            log_tool_call(name, args, "denied", None, elapsed(start))
            return deny_message(DENY_USER, request)
    return await execute(request)


def deny_sync_tool_call(
    request: ToolCallRequest,
    execute: SyncExecute,  # pylint: disable=unused-argument
) -> ToolMessage:
    """Refuse a call on the sync path, which has no approval prompt; never run it.

    Args:
        request: The tool call from ``ToolNode``.
        execute: Not called.

    Returns:
        A ``DENY_UNAVAILABLE`` denial ``ToolMessage``.
    """
    start = time.monotonic()
    call = request.tool_call
    log_tool_call(call["name"], call["args"], "denied", None, elapsed(start))
    return deny_message(DENY_UNAVAILABLE, request)


def make_tool_node(
    tools: Sequence[BaseTool], modes: Mapping[str, PermissionMode]
) -> ToolNode:
    """Return a ``ToolNode`` for *tools* gated by *modes*.

    Args:
        tools: The bound tools; none may be ``deny`` or missing from *modes*.
        modes: ``{tool name: mode}`` for every configured tool, ``deny`` included.

    Returns:
        The gated ``ToolNode``.

    Raises:
        ValueError: A bound tool is missing from *modes* or mapped to ``deny``.
    """
    for tool in tools:
        if modes.get(tool.name, "deny") == "deny":
            raise ValueError(
                f"bound tool {tool.name!r} is missing from the modes or mapped to deny"
            )
    # The default handler re-raises everything except ToolInvocationError; with True
    # every tool exception becomes an error ToolMessage (its text goes to the provider)
    # and the turn continues. asyncio.CancelledError is not an Exception and propagates.
    return ToolNode(
        list(tools),
        handle_tool_errors=True,
        awrap_tool_call=functools.partial(gate_tool_call, modes=modes),
        wrap_tool_call=deny_sync_tool_call,
    )
