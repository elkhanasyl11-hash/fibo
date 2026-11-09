"""Request ID middleware.

Every request gets an id: the client's X-Request-ID header if it looks safe, otherwise a new UUID4.
The id is
  - stored in a context variable so every log line of this request carries it,
  - stored in request.state.request_id so error handlers can put it into the error body,
  - returned to the client in the X-Request-ID response header.

Written as a plain ASGI middleware (not BaseHTTPMiddleware) so it does not buffer responses and
works the same for normal responses and for errors.
"""

import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

HEADER = "x-request-id"
# Accept only short ids made of safe characters, to keep log lines clean (no log injection).
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _pick_request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.decode("latin-1").lower() == HEADER:
            candidate = value.decode("latin-1")
            if _SAFE_ID.match(candidate):
                return candidate
    return uuid.uuid4().hex


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _pick_request_id(scope)
        # scope["state"] is what request.state reads; the error handlers read the id from there.
        scope.setdefault("state", {})["request_id"] = request_id
        request_id_var.set(request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Drop a header the error handlers may already have set, so it appears once.
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != HEADER.encode()]
                headers.append((HEADER.encode("latin-1"), request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)
