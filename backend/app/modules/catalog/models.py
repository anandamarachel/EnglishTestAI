"""Persistent domain models; business operations are implemented in services."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Topic(Base):
    __tablename__ = "topics"

    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),)

    topic_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class AIPersona(Base):
    __tablename__ = "ai_personas"

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(btrim(role_description)) > 0", name="role_description_not_blank"),
        CheckConstraint(
            "length(btrim(behavior_instructions)) > 0", name="behavior_instructions_not_blank"
        ),
        CheckConstraint("length(btrim(voice_key)) > 0", name="voice_key_not_blank"),
    )

    persona_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_description: Mapped[str] = mapped_column(Text, nullable=False)
    behavior_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    voice_key: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
