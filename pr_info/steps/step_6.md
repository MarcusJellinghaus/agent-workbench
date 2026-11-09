# Step 6 – Origin-check ASGI middleware

## LLM prompt
Read `pr_info/steps/summary.md` and this file. Implement step 6: a plain ASGI middleware
in `apps/origin_check.py` that rejects HTTP and WebSocket requests carrying a foreign
`Origin` header. Tests first, then code; all checks pass; one commit.

## WHERE
- Create `src/agent_workbench/apps/origin_check.py`
- Create `tests/apps/test_origin_check.py`

## WHAT
```python
def local_origins(port: int) -> list[str]:
    """Return ["http://127.0.0.1:<port>", "http://localhost:<port>"]."""

class OriginCheckMiddleware:
    def __init__(self, app: Any, allowed_origins: Sequence[str]) -> None: ...
    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None: ...
```

## HOW
- Standard library only: no `starlette`, `fastapi` or Chainlit imports. `app: Any` so mypy
  accepts the class for `add_middleware` (step 9).
- Module docstring states why: Chainlit's Socket.IO server is created with
  `cors_allowed_origins=[]` (origin check off) and `allow_origins` covers HTTP CORS only, so
  another website open in the browser could otherwise open the socket and chat with the
  user's key.
- `local_origins` is also used by the `config.toml` writer (step 7), so origins are defined once.

## ALGORITHM
```
if scope["type"] not in ("http", "websocket"): return await app(scope, receive, send)
origin = first value of header b"origin" in scope["headers"], decoded latin-1, or None
if origin is None or origin in allowed: return await app(scope, receive, send)
http      → send {"type": "http.response.start", "status": 403, headers text/plain}; send body b"Forbidden origin"
websocket → await receive() (websocket.connect); send {"type": "websocket.close", "code": 1008}
log a warning with the rejected origin
```

## DATA
No return values; rejected requests get HTTP 403 / WebSocket close 1008.

## Tests (`tests/apps/test_origin_check.py`)
Dummy ASGI app records whether it was called; `send` collects messages into a list.
- HTTP with `Origin: http://evil.example` → 403, dummy app not called.
- HTTP with `Origin: http://127.0.0.1:8000` and with `http://localhost:8000` → passed through.
- HTTP without `Origin` → passed through.
- WebSocket with a foreign origin → `websocket.close` code 1008, dummy app not called;
  with a local origin → passed through.
- `Origin: null` → rejected.
- `lifespan` scope → passed through.
- `local_origins(8123)` returns both origins with that port.

## Checks / commit
pylint, pytest, mypy, ruff, vulture. Commit: `feat(apps): origin check middleware`.
