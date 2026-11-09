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
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIJob(Base):
    __tablename__ = "ai_jobs"

    __table_args__ = (
        CheckConstraint(
            (
                "job_type IN ('generate_exercise', 'evaluate_attempt', 'grade_answer', "
                "'start_conversation', 'process_voice_turn')"
            ),
            name="job_type_values",
        ),
        CheckConstraint(
            (
                "status IN ('queued', 'running', 'cancel_requested', 'succeeded', "
                "'failed', 'cancelled')"
            ),
            name="status_values",
        ),
        CheckConstraint("execution_version > 0", name="execution_version_positive"),
        CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint(
            "num_nonnulls(exercise_id, attempt_id, answer_id, message_id) = 1", name="one_target"
        ),
        CheckConstraint(
            (
                "(job_type = 'generate_exercise' AND exercise_id IS NOT NULL) OR "
                "(job_type IN ('evaluate_attempt','start_conversation') AND attempt_id "
                "IS NOT NULL) OR (job_type = 'grade_answer' AND answer_id IS NOT NULL) "
                "OR (job_type = 'process_voice_turn' AND message_id IS NOT NULL)"
            ),
            name="target_type",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts", name="attempt_bounds"
        ),
        CheckConstraint(
            "status <> 'cancel_requested' OR cancel_requested_at IS NOT NULL",
            name="cancel_timestamp",
        ),
        CheckConstraint(
            "(status IN ('succeeded','failed','cancelled')) = (finished_at IS NOT NULL)",
            name="finished_time",
        ),
        CheckConstraint(
            "status <> 'running' OR (lease_expires_at IS NOT NULL AND started_at IS NOT NULL)",
            name="running_lease",
        ),
        CheckConstraint("jsonb_typeof(result_refs) = 'object'", name="result_refs_shape"),
        Index("ix_ai_jobs_requested_by_created_at", "requested_by", "created_at"),
        Index(
            "ix_ai_jobs_status_next_retry_at_created_at", "status", "next_retry_at", "created_at"
        ),
        Index("ix_ai_jobs_exercise_id", "exercise_id"),
        Index("ix_ai_jobs_attempt_id", "attempt_id"),
        Index("ix_ai_jobs_answer_id", "answer_id"),
        Index("ix_ai_jobs_message_id", "message_id"),
        Index(
            "uq_ai_jobs_active_exercise_id",
            "exercise_id",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'running', 'cancel_requested') AND exercise_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_ai_jobs_active_answer_id",
            "answer_id",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'running', 'cancel_requested') AND answer_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_ai_jobs_active_message_id",
            "message_id",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'running', 'cancel_requested') AND message_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_ai_jobs_active_attempt_type",
            "attempt_id",
            "job_type",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'running', 'cancel_requested') AND attempt_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_ai_jobs_queued",
            "next_retry_at",
            "created_at",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    requested_by: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    exercise_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
    attempt_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "attempts.attempt_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
    answer_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("answers.answer_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "conversation_messages.message_id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'queued'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    result_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class APIIdempotencyKey(Base):
    __tablename__ = "api_idempotency_keys"

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed')", name="status_values"),
        CheckConstraint("length(btrim(operation)) > 0", name="operation_not_blank"),
        CheckConstraint("expires_at > created_at", name="valid_expiry"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        CheckConstraint(
            (
                "(status = 'pending' AND response_status IS NULL) OR (status = "
                "'completed' AND response_status BETWEEN 200 AND 299)"
            ),
            name="response_state",
        ),
        CheckConstraint("jsonb_typeof(result_refs) = 'object'", name="result_refs_shape"),
        UniqueConstraint("user_id", "idempotency_key"),
    )

    idempotency_record_id: Mapped[UUID] = mapped_column(
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
    idempotency_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
