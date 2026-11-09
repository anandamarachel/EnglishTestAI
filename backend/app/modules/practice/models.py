"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attempt(Base):
    __tablename__ = "attempts"

    __table_args__ = (
        CheckConstraint(
            (
                "status IN ('in_progress', 'submitted', 'evaluating', 'completed', "
                "'failed', 'cancelled')"
            ),
            name="status_values",
        ),
        CheckConstraint(
            (
                "current_stage IN ('writing', 'reading', 'quiz', 'listening', "
                "'conversation', 'evaluation', 'results')"
            ),
            name="current_stage_values",
        ),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(
            "source_attempt_id IS NULL OR source_attempt_id <> attempt_id", name="source_not_self"
        ),
        CheckConstraint(
            (
                "last_activity_at >= started_at AND (last_saved_at IS NULL OR "
                "last_saved_at >= started_at) AND (submitted_at IS NULL OR submitted_at"
                " >= started_at) AND (completed_at IS NULL OR (submitted_at IS NOT NULL"
                " AND completed_at >= submitted_at))"
            ),
            name="valid_times",
        ),
        CheckConstraint(
            (
                "status NOT IN ('submitted','evaluating','completed','failed') OR "
                "submitted_at IS NOT NULL"
            ),
            name="submitted_states",
        ),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_time"
        ),
        UniqueConstraint("user_id", "exercise_id", "attempt_number"),
        Index("ix_attempts_user_id_last_activity_at", "user_id", "last_activity_at"),
        Index("ix_attempts_exercise_id", "exercise_id"),
        Index("ix_attempts_source_attempt_id", "source_attempt_id"),
    )

    attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_attempt_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "attempts.attempt_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'in_progress'")
    )
    current_stage: Mapped[str] = mapped_column(String(24), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
