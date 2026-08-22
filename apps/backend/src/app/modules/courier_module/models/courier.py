"""Таблица `couriers`: корень aggregate курьера."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.modules.courier_module.models.document import CourierDocument
    from app.modules.courier_module.models.platform_account import CourierPlatformAccount


class Courier(UUIDPkMixin, TimestampMixin, Base):
    """Курьер с естественными ключами email и phone."""

    __tablename__ = "couriers"
    __patchable__ = frozenset(
        {
            "full_name",
            "email",
            "phone",
            "date_of_birth",
            "city",
            "address",
            "citizenship",
            "bank_account",
            "contact_platform",
            "contact",
            "source",
            "consent_to_processing",
        }
    )
    __table_args__ = (
        UniqueConstraint("email"),
        UniqueConstraint("phone"),
        CheckConstraint(
            "(consent_to_processing IS TRUE AND consent_at IS NOT NULL) OR "
            "(consent_to_processing IS FALSE AND consent_at IS NULL)",
            name="consent_state",
        ),
    )

    full_name: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(16))
    date_of_birth: Mapped[date]
    city: Mapped[str | None] = mapped_column(String(128), default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    citizenship: Mapped[str | None] = mapped_column(String(128), default=None)
    bank_account: Mapped[str | None] = mapped_column(String(64), default=None)
    contact_platform: Mapped[str | None] = mapped_column(String(32), default=None)
    contact: Mapped[str | None] = mapped_column(String(255), default=None)
    source: Mapped[str | None] = mapped_column(String(64), default=None)
    consent_to_processing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(default=None)

    platform_accounts: Mapped[list["CourierPlatformAccount"]] = relationship(
        back_populates="courier",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    documents: Mapped[list["CourierDocument"]] = relationship(
        back_populates="courier",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


Index("ix_couriers_keyset", Courier.created_at.desc(), Courier.id.desc())
