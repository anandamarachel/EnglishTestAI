"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Exercise(Base):
    __tablename__ = "exercises"

    __table_args__ = (
        CheckConstraint(
            "topic_selection IN ('catalog', 'custom', 'random')", name="topic_selection_values"
        ),
        CheckConstraint(
            "skill IN ('writing', 'reading', 'listening', 'speaking')", name="skill_values"
        ),
        CheckConstraint(
            "difficulty IN ('beginner', 'intermediate', 'advanced')", name="difficulty_values"
        ),
        CheckConstraint(
            "content_cefr_level IN ('A2', 'B1', 'B2')", name="content_cefr_level_values"
        ),
        CheckConstraint("content_source IN ('ai', 'prepared')", name="content_source_values"),
        CheckConstraint(
            "generation_status IN ('pending', 'generating', 'ready', 'failed', 'cancelled')",
            name="generation_status_values",
        ),
        CheckConstraint(
            (
                "(topic_selection = 'catalog' AND topic_id IS NOT NULL AND custom_topic"
                " IS NULL) OR (topic_selection = 'custom' AND topic_id IS NULL AND "
                "custom_topic IS NOT NULL AND length(btrim(custom_topic)) > 0) OR "
                "(topic_selection = 'random' AND custom_topic IS NULL AND "
                "(generation_status <> 'ready' OR topic_id IS NOT NULL))"
            ),
            name="topic_choice",
        ),
        CheckConstraint(
            (
                "generation_status <> 'ready' OR (title IS NOT NULL AND "
                "length(btrim(title)) > 0 AND instructions IS NOT NULL AND "
                "length(btrim(instructions)) > 0)"
            ),
            name="ready_content",
        ),
        CheckConstraint(
            (
                "(difficulty = 'beginner' AND content_cefr_level = 'A2') OR (difficulty"
                " = 'intermediate' AND content_cefr_level = 'B1') OR (difficulty = "
                "'advanced' AND content_cefr_level = 'B2')"
            ),
            name="level_mapping",
        ),
        CheckConstraint(
            "jsonb_typeof(generation_config) = 'object'", name="generation_config_shape"
        ),
        Index("ix_exercises_created_by_skill_created_at", "created_by", "skill", "created_at"),
        Index("ix_exercises_topic_id", "topic_id"),
    )

    exercise_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    created_by: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    topic_selection: Mapped[str] = mapped_column(String(16), nullable=False)
    topic_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("topics.topic_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    custom_topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    skill: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    content_cefr_level: Mapped[str] = mapped_column(String(2), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ai'")
    )
    generation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    generation_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generator_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
