"""Persistent domain models; business operations are implemented in services."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
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


class ReadingExercise(Base):
    __tablename__ = "reading_exercises"

    __table_args__ = (
        CheckConstraint("feedback_mode IN ('per_question')", name="feedback_mode_values"),
        CheckConstraint("length(btrim(passage)) > 0", name="passage_not_blank"),
        CheckConstraint(
            "requested_word_count IS NULL OR requested_word_count > 0",
            name="requested_word_count_positive",
        ),
        CheckConstraint("question_count > 0", name="question_count_positive"),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "exercises.exercise_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    passage: Mapped[str] = mapped_column(Text, nullable=False)
    requested_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'per_question'")
    )


class ReadingAttempt(Base):
    __tablename__ = "reading_attempts"

    __table_args__ = (
        CheckConstraint("paragraph_index >= 0", name="paragraph_index_nonnegative"),
        CheckConstraint("offset_in_paragraph >= 0", name="offset_in_paragraph_nonnegative"),
        Index("ix_reading_attempts_current_question_id", "current_question_id"),
    )

    attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "attempts.attempt_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        primary_key=True,
        nullable=False,
    )
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    offset_in_paragraph: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    current_question_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "questions.question_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        ),
        nullable=True,
    )


class ExerciseVocabulary(Base):
    __tablename__ = "exercise_vocabulary"

    __table_args__ = (
        CheckConstraint("length(btrim(word_or_phrase)) > 0", name="word_or_phrase_not_blank"),
        CheckConstraint("length(btrim(meaning)) > 0", name="meaning_not_blank"),
        CheckConstraint("length(btrim(example_sentence)) > 0", name="example_sentence_not_blank"),
        CheckConstraint(
            "length(btrim(example_from_passage)) > 0", name="example_from_passage_not_blank"
        ),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("jsonb_typeof(occurrences) = 'array'", name="occurrences_shape"),
        UniqueConstraint("exercise_id", "position"),
    )

    vocabulary_item_id: Mapped[UUID] = mapped_column(
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
    word_or_phrase: Mapped[str] = mapped_column(String(200), nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    example_sentence: Mapped[str] = mapped_column(Text, nullable=False)
    example_from_passage: Mapped[str] = mapped_column(Text, nullable=False)
    occurrences: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
