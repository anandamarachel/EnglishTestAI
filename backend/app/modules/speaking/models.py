"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SpeakingExercise(Base):
    __tablename__ = "speaking_exercises"

    __table_args__ = (
        CheckConstraint("length(btrim(rubric_version)) > 0", name="rubric_version_not_blank"),
        CheckConstraint("jsonb_typeof(persona_snapshot) = 'object'", name="persona_snapshot_shape"),
        CheckConstraint("jsonb_typeof(rubric_snapshot) = 'object'", name="rubric_snapshot_shape"),
        Index("ix_speaking_exercises_persona_id", "persona_id"),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    persona_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_personas.persona_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    persona_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'ended')", name="status_values"),
        CheckConstraint("next_position > 0", name="next_position_positive"),
        CheckConstraint("(status = 'ended') = (ended_at IS NOT NULL)", name="ended_time"),
    )

    conversation_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "attempts.attempt_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    provider_session_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    __table_args__ = (
        CheckConstraint("sender IN ('user', 'assistant')", name="sender_values"),
        CheckConstraint(
            "transcription_status IN ('pending', 'completed', 'failed', 'not_applicable')",
            name="transcription_status_values",
        ),
        CheckConstraint(
            "delivery_status IN ('pending', 'processing', 'ready', 'failed', 'cancelled')",
            name="delivery_status_values",
        ),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint(
            (
                "reply_to_message_id IS NULL OR (sender = 'assistant' AND "
                "reply_to_message_id <> message_id)"
            ),
            name="reply_sender",
        ),
        CheckConstraint(
            "sender <> 'assistant' OR transcription_status = 'not_applicable'",
            name="assistant_transcription",
        ),
        CheckConstraint(
            (
                "transcription_status <> 'completed' OR (transcript IS NOT NULL AND "
                "length(btrim(transcript)) > 0)"
            ),
            name="completed_transcript",
        ),
        UniqueConstraint("conversation_session_id", "position"),
        UniqueConstraint("conversation_session_id", "client_message_key"),
        Index("ix_conversation_messages_audio_media_id", "audio_media_id"),
        Index(
            "uq_conversation_messages_greeting",
            "conversation_session_id",
            unique=True,
            postgresql_where=text("sender = 'assistant' AND reply_to_message_id IS NULL"),
        ),
    )

    message_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    conversation_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "conversation_sessions.conversation_session_id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    )
    client_message_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reply_to_message_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "conversation_messages.message_id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        unique=True,
        nullable=True,
    )
    sender: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_media_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "media_assets.media_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
    transcription_status: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
