from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.exercises.schemas import Difficulty, RandomTopic, Strict, TopicSelection
from app.modules.jobs.schemas import JobOut
from app.modules.media.schemas import MediaOut


class CreateSpeakingExerciseRequest(Strict):
    difficulty: Difficulty
    topic: TopicSelection = Field(default_factory=lambda: RandomTopic(mode="random"))
    persona_id: UUID


class ConversationOut(BaseModel):
    conversation_session_id: UUID
    attempt_id: UUID
    status: Literal["active", "paused", "ended"]
    last_activity_at: datetime
    ended_at: datetime | None
    # The one voice job (greeting or turn) still in progress, if any.
    active_job: JobOut | None


class MessageOut(BaseModel):
    message_id: UUID
    sender: Literal["user", "assistant"]
    position: int
    client_message_key: UUID
    reply_to_message_id: UUID | None
    transcript: str | None
    audio: MediaOut | None
    transcription_status: Literal["pending", "completed", "failed", "not_applicable"]
    delivery_status: Literal["pending", "processing", "ready", "failed", "cancelled"]
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None


class VoiceTurnResult(BaseModel):
    message: MessageOut
    job: JobOut
