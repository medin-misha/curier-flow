"""Таблица `admins`: административные учётные записи."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class Admin(UUIDPkMixin, TimestampMixin, Base):
    """Администратор с версией credentials и необязательным Telegram ID."""

    __tablename__ = "admins"
    __patchable__ = frozenset({"username", "telegram_id"})
    __table_args__ = (
        UniqueConstraint("username"),
        UniqueConstraint("telegram_id"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        CheckConstraint("telegram_id IS NULL OR telegram_id > 0", name="telegram_id_positive"),
        CheckConstraint("auth_version > 0", name="auth_version_positive"),
    )

    username: Mapped[str] = mapped_column(String(64))
    hashed_password: Mapped[str] = mapped_column(String(512))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    auth_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))


Index("ix_admins_keyset", Admin.created_at.desc(), Admin.id.desc())
