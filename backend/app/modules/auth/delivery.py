"""Password-reset message delivery.

No real email provider is configured yet. Available sinks:
- outbox:   development only; writes each message to a private local file.
- memory:   tests only; keeps messages in a list.
- disabled: forgot-password answers 503 for every email (production default until a
            provider is chosen), so the app never claims a message was sent.
Tokens are never logged or returned by the API.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from anyio import to_thread


@dataclass(frozen=True)
class ResetMessage:
    email: str
    display_name: str
    token: str
    expires_at: datetime


class ResetDelivery(Protocol):
    enabled: bool

    async def send(self, message: ResetMessage) -> None: ...


class DisabledDelivery:
    enabled = False

    async def send(self, message: ResetMessage) -> None:  # pragma: no cover - never called
        raise RuntimeError("Password reset delivery is not configured")


class MemoryDelivery:
    enabled = True

    def __init__(self) -> None:
        self.sent: list[ResetMessage] = []

    async def send(self, message: ResetMessage) -> None:
        self.sent.append(message)


class OutboxDelivery:
    """Local stand-in for email: one owner-readable text file per message."""

    enabled = True

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    async def send(self, message: ResetMessage) -> None:
        await to_thread.run_sync(self._write, message)

    def _write(self, message: ResetMessage) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        path = self.directory / f"{stamp}-{uuid4().hex[:8]}-password-reset.txt"
        body = (
            f"To: {message.email}\n"
            "Subject: Reset your English Day password\n\n"
            f"Hi {message.display_name},\n\n"
            "Use this token to choose a new password:\n\n"
            f"{message.token}\n\n"
            f"It expires at {message.expires_at.isoformat()} and works once.\n"
            "If you did not ask for this, ignore this message.\n"
        )
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(body)
