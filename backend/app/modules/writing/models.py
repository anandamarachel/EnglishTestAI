"""Persistent domain models; business operations are implemented in services."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WritingExercise(Base):
    __tablename__ = "writing_exercises"

    __table_args__ = (
        CheckConstraint("length(btrim(rubric_version)) > 0", name="rubric_version_not_blank"),
        CheckConstraint(
            "target_word_count IS NULL OR target_word_count > 0", name="target_word_count_positive"
        ),
        CheckConstraint("jsonb_typeof(rubric_snapshot) = 'object'", name="rubric_snapshot_shape"),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    target_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class WritingAttempt(Base):
    __tablename__ = "writing_attempts"

    attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "attempts.attempt_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
