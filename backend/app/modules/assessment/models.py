"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="status_values",
        ),
        CheckConstraint("length(btrim(rubric_version)) > 0", name="rubric_version_not_blank"),
        CheckConstraint(
            (
                "(overall_score IS NULL AND max_score IS NULL) OR (overall_score IS NOT"
                " NULL AND max_score IS NOT NULL AND max_score > 0 AND overall_score >="
                " 0 AND overall_score <= max_score)"
            ),
            name="score_pair",
        ),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_time"
        ),
        CheckConstraint(
            "status = 'completed' OR overall_score IS NULL", name="score_requires_completion"
        ),
        CheckConstraint("jsonb_typeof(rubric_snapshot) = 'object'", name="rubric_snapshot_shape"),
        CheckConstraint("jsonb_typeof(feedback_payload) = 'object'", name="feedback_payload_shape"),
    )

    evaluation_id: Mapped[UUID] = mapped_column(
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
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text('\'{"schema_version": 1,"corrections":[],"limitations":[]}\'::jsonb'),
    )
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CriterionResult(Base):
    __tablename__ = "criterion_results"

    __table_args__ = (
        CheckConstraint(
            "assessment_status IN ('assessed', 'not_assessed')", name="assessment_status_values"
        ),
        CheckConstraint("length(btrim(criterion_code)) > 0", name="criterion_code_not_blank"),
        CheckConstraint("length(btrim(feedback)) > 0", name="feedback_not_blank"),
        CheckConstraint(
            (
                "(assessment_status = 'not_assessed' AND score IS NULL AND max_score IS"
                " NULL) OR (assessment_status = 'assessed' AND score IS NOT NULL AND "
                "max_score IS NOT NULL AND max_score > 0 AND score >= 0 AND score <= "
                "max_score)"
            ),
            name="assessment_score",
        ),
        UniqueConstraint("evaluation_id", "criterion_code"),
    )

    criterion_result_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    evaluation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "evaluations.evaluation_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    criterion_code: Mapped[str] = mapped_column(String(40), nullable=False)
    assessment_status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
