"""ASGI middleware rejecting requests whose ``Origin`` header is not the local UI.

Chainlit creates its Socket.IO server with ``cors_allowed_origins=[]``, which turns the
Socket.IO origin check off, and its ``allow_origins`` setting covers HTTP CORS only.
Without this middleware another website open in the browser could open the socket and
chat with the user's key. Requests without an ``Origin`` header (same-origin GETs,
non-browser clients) pass.
"""

import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)


def local_origins(port: int) -> list[str]:
    """Return the origins of the local UI on ``port``."""
    return [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]


def _origin(scope: dict[str, Any]) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"origin":
            return bytes(value).decode("latin-1")
    return None


class OriginCheckMiddleware:  # pylint: disable=too-few-public-methods
    """Reject HTTP (403) and WebSocket (close 1008) requests from foreign origins."""

    def __init__(self, app: Any, allowed_origins: Sequence[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Pass the request on, or answer it with a rejection for a foreign origin."""
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        origin = _origin(scope)
        if origin is None or origin in self.allowed_origins:
            await self.app(scope, receive, send)
            return
        logger.warning("Rejected request from foreign origin %r", origin)
        if scope["type"] == "http":
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                }
            )
            await send({"type": "http.response.body", "body": b"Forbidden origin"})
        else:
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 1008})
