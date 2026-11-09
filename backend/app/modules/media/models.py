"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('listening_audio', 'speaking_user_audio', 'speaking_ai_audio')",
            name="purpose_values",
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'deleted')", name="status_values"
        ),
        CheckConstraint("length(btrim(storage_key)) > 0", name="storage_key_not_blank"),
        CheckConstraint("length(btrim(mime_type)) > 0", name="mime_type_not_blank"),
        CheckConstraint(
            "size_bytes >= 0 AND (duration_ms IS NULL OR duration_ms >= 0)", name="size_nonnegative"
        ),
        CheckConstraint("expires_at IS NULL OR expires_at > created_at", name="valid_expiry"),
        Index("ix_media_assets_owner_user_id_created_at", "owner_user_id", "created_at"),
    )

    media_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
