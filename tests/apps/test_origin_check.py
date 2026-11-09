"""``OriginCheckMiddleware``: foreign origins are rejected for HTTP and WebSocket."""

from typing import Any

import pytest

from agent_workbench.apps.origin_check import OriginCheckMiddleware, local_origins

ALLOWED = local_origins(8000)


class _DummyApp:
    """ASGI app that records whether it was called."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.called = True


def _scope(scope_type: str, origin: str | None) -> dict[str, Any]:
    headers = [(b"host", b"127.0.0.1:8000")]
    if origin is not None:
        headers.append((b"origin", origin.encode("latin-1")))
    return {"type": scope_type, "headers": headers}


async def _run(scope: dict[str, Any]) -> tuple[_DummyApp, list[dict[str, Any]]]:
    app = _DummyApp()
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await OriginCheckMiddleware(app, ALLOWED)(scope, receive, send)
    return app, sent


async def test_http_foreign_origin_gets_403() -> None:
    app, sent = await _run(_scope("http", "http://evil.example"))

    assert not app.called
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 403
    assert sent[1] == {"type": "http.response.body", "body": b"Forbidden origin"}


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8000", "http://localhost:8000"])
async def test_http_local_origin_passes(origin: str) -> None:
    app, sent = await _run(_scope("http", origin))

    assert app.called
    assert not sent


async def test_http_without_origin_passes() -> None:
    app, sent = await _run(_scope("http", None))

    assert app.called
    assert not sent


async def test_websocket_foreign_origin_is_closed_1008() -> None:
    app, sent = await _run(_scope("websocket", "http://evil.example"))

    assert not app.called
    assert sent == [{"type": "websocket.close", "code": 1008}]


async def test_websocket_local_origin_passes() -> None:
    app, sent = await _run(_scope("websocket", "http://localhost:8000"))

    assert app.called
    assert not sent


async def test_null_origin_is_rejected() -> None:
    app, sent = await _run(_scope("http", "null"))

    assert not app.called
    assert sent[0]["status"] == 403


async def test_lifespan_scope_passes() -> None:
    app, sent = await _run({"type": "lifespan"})

    assert app.called
    assert not sent


def test_local_origins_uses_port() -> None:
    assert local_origins(8123) == ["http://127.0.0.1:8123", "http://localhost:8123"]
