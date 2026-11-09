"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Question(Base):
    __tablename__ = "questions"

    __table_args__ = (
        CheckConstraint(
            "question_type IN ('multiple_choice', 'short_answer')", name="question_type_values"
        ),
        CheckConstraint("grading_method IN ('answer_key', 'rubric')", name="grading_method_values"),
        CheckConstraint("length(btrim(question_text)) > 0", name="question_text_not_blank"),
        CheckConstraint(
            "length(btrim(reference_explanation)) > 0", name="reference_explanation_not_blank"
        ),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("max_points > 0", name="max_points_positive"),
        CheckConstraint(
            (
                "(question_type = 'multiple_choice' AND grading_method = 'answer_key' "
                "AND reference_answer IS NULL AND rubric_version IS NULL AND "
                "rubric_snapshot IS NULL) OR (question_type = 'short_answer' AND "
                "grading_method = 'rubric' AND reference_answer IS NOT NULL AND "
                "length(btrim(reference_answer)) > 0 AND rubric_version IS NOT NULL AND"
                " length(btrim(rubric_version)) > 0 AND rubric_snapshot IS NOT NULL)"
            ),
            name="grading_configuration",
        ),
        CheckConstraint("jsonb_typeof(evidence_spans) = 'array'", name="evidence_spans_shape"),
        CheckConstraint(
            "rubric_snapshot IS NULL OR jsonb_typeof(rubric_snapshot) = 'object'",
            name="rubric_snapshot_shape",
        ),
        UniqueConstraint("exercise_id", "position"),
    )

    question_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    question_type: Mapped[str] = mapped_column(String(24), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_spans: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    grading_method: Mapped[str] = mapped_column(String(16), nullable=False)
    rubric_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rubric_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    max_points: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)


class QuestionOption(Base):
    __tablename__ = "question_options"

    __table_args__ = (
        CheckConstraint("length(btrim(option_text)) > 0", name="option_text_not_blank"),
        CheckConstraint("position > 0", name="position_positive"),
        UniqueConstraint("question_id", "position"),
    )

    option_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    question_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "questions.question_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Answer(Base):
    __tablename__ = "answers"

    __table_args__ = (
        CheckConstraint(
            "grading_status IN ('pending', 'processing', 'graded', 'failed', 'cancelled')",
            name="grading_status_values",
        ),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(
            "selected_option_id IS NULL OR response_text IS NULL", name="one_answer_format"
        ),
        CheckConstraint(
            (
                "submitted_at IS NULL OR selected_option_id IS NOT NULL OR "
                "(response_text IS NOT NULL AND length(btrim(response_text)) > 0)"
            ),
            name="submitted_not_empty",
        ),
        CheckConstraint(
            (
                "(grading_status = 'graded' AND submitted_at IS NOT NULL AND "
                "awarded_points IS NOT NULL AND awarded_points >= 0) OR (grading_status"
                " <> 'graded' AND awarded_points IS NULL)"
            ),
            name="grade_consistency",
        ),
        CheckConstraint(
            "grading_status = 'pending' OR submitted_at IS NOT NULL",
            name="grading_requires_submission",
        ),
        UniqueConstraint("attempt_id", "question_id"),
        Index("ix_answers_question_id", "question_id"),
        Index("ix_answers_selected_option_id", "selected_option_id"),
    )

    answer_id: Mapped[UUID] = mapped_column(
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
        nullable=False,
    )
    question_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "questions.question_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=False,
    )
    selected_option_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "question_options.option_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grading_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    awarded_points: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    grading_model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now()
    )
