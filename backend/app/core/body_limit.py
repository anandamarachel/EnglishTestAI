"""Reject request bodies above max_request_bytes with 413 before any handler runs."""

import json
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = next((v for k, v in scope["headers"] if k == b"content-length"), None)
        if length is not None:
            try:
                too_large = int(length) > self.max_bytes
            except ValueError:
                too_large = True
            if too_large:
                await self._reject(scope, send)
                return
            await self.app(scope, receive, send)
            return
        # No Content-Length (chunked): buffer up to the limit, then replay to the app.
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await self._reject(scope, send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        body = json.dumps(
            {
                "code": "CAPACITY_EXCEEDED",
                "message": "Request is too large. Your draft has not been changed.",
                "request_id": scope.get("state", {}).get("request_id") or str(uuid4()),
                "retryable": False,
                "details": [],
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
