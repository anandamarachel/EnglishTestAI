"""Persistent domain models; business operations are implemented in services."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListeningExercise(Base):
    __tablename__ = "listening_exercises"

    __table_args__ = (
        CheckConstraint("feedback_mode IN ('after_submission')", name="feedback_mode_values"),
        CheckConstraint(
            "transcript_policy IN ('after_submission')", name="transcript_policy_values"
        ),
        CheckConstraint("length(btrim(transcript)) > 0", name="transcript_not_blank"),
        CheckConstraint("question_count > 0", name="question_count_positive"),
        Index("ix_listening_exercises_audio_media_id", "audio_media_id"),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    audio_media_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "media_assets.media_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'after_submission'")
    )
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'after_submission'")
    )


class ListeningAttempt(Base):
    __tablename__ = "listening_attempts"

    __table_args__ = (
        CheckConstraint("playback_position_ms >= 0", name="position_nonnegative"),
        Index("ix_listening_attempts_current_question_id", "current_question_id"),
    )

    attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "attempts.attempt_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    playback_position_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    current_question_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "questions.question_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
