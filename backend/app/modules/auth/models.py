"""Persistent domain models; business operations are implemented in services."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at AND (revoked_at IS NULL OR revoked_at >= created_at)",
            name="valid_times",
        ),
        Index("ix_auth_sessions_user_id", "user_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
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
    refresh_token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at AND (used_at IS NULL OR used_at >= created_at)",
            name="valid_times",
        ),
        Index("ix_password_reset_tokens_user_id", "user_id"),
    )

    reset_id: Mapped[UUID] = mapped_column(
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
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
