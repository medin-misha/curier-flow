"""Таблица `admin_refresh_tokens`: одноразовые refresh-сессии."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base


class AdminRefreshToken(Base):
    """Хеш refresh JWT и состояние его ротации."""

    __tablename__ = "admin_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        CheckConstraint("auth_version > 0", name="auth_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    admin_id: Mapped[UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"),
    )
    family_id: Mapped[UUID]
    token_hash: Mapped[str] = mapped_column(String(64))
    auth_version: Mapped[int]
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


Index(
    "ix_admin_refresh_tokens_admin_active",
    AdminRefreshToken.admin_id,
    AdminRefreshToken.revoked_at,
)
Index(
    "ix_admin_refresh_tokens_family_active",
    AdminRefreshToken.family_id,
    AdminRefreshToken.revoked_at,
)
Index("ix_admin_refresh_tokens_expires_at", AdminRefreshToken.expires_at)
