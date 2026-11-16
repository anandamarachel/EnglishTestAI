from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class MediaOut(BaseModel):
    media_id: UUID
    purpose: Literal["listening_audio", "speaking_user_audio", "speaking_ai_audio"]
    mime_type: str
    size_bytes: int
    duration_ms: int | None
    status: Literal["pending", "ready", "failed", "deleted"]
    # False once deleted or expired; results that used the audio stay readable.
    available: bool
