"""Per-request UUID returned in X-Request-ID and in every error body."""

from uuid import UUID, uuid4

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-ID"


def _client_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            try:
                return str(UUID(value.decode("ascii")))
            except ValueError, UnicodeDecodeError:
                return None
    return None


class RequestIdMiddleware:
    """Accept a client-supplied UUID for tracing; otherwise generate one."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _client_request_id(scope) or str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((HEADER.lower().encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = str(uuid4())
        request.state.request_id = request_id
    return request_id
