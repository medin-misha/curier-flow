"""Таблица `courier_transports`: история аренды транспорта курьерами."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin
from app.platform.files import File

if TYPE_CHECKING:
    from app.modules.transport_module.models.transport import Transport


class RentalPaymentType(StrEnum):
    """Периодичность оплаты аренды, включая оплату прошедшей недели."""

    MONTHLY = "monthly"
    WEEKLY = "weekly"
    WEEKLY_IN_ARREARS = "weekly_in_arrears"


class CourierTransport(UUIDPkMixin, TimestampMixin, Base):
    """Полуоткрытый период аренды `[started_at, ended_at)` и договор."""

    __tablename__ = "courier_transports"
    __patchable__ = frozenset({"payment_type"})

    transport_id: Mapped[UUID] = mapped_column(ForeignKey("transports.id", ondelete="CASCADE"))
    courier_id: Mapped[UUID] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    payment_type: Mapped[RentalPaymentType | None] = mapped_column(
        Enum(
            RentalPaymentType,
            name="rental_payment_type",
            native_enum=False,
            length=32,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=None,
    )
    file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id", ondelete="RESTRICT"),
        default=None,
    )

    __table_args__ = (
        UniqueConstraint("file_id"),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="period_order"),
        CheckConstraint(
            "payment_type IS NULL OR payment_type IN ('monthly', 'weekly', 'weekly_in_arrears')",
            name="payment_type_allowed",
        ),
        ExcludeConstraint(
            (transport_id, "="),
            (func.tstzrange(started_at, ended_at, "[)"), "&&"),
            name="excl_courier_transports_transport_period",
            using="gist",
        ),
        ExcludeConstraint(
            (courier_id, "="),
            (func.tstzrange(started_at, ended_at, "[)"), "&&"),
            name="excl_courier_transports_courier_period",
            using="gist",
        ),
    )

    transport: Mapped["Transport"] = relationship(back_populates="rentals")
    file: Mapped[File | None] = relationship(lazy="joined")

    @property
    def is_active(self) -> bool:
        """Показать, что период аренды ещё не завершён."""
        return self.ended_at is None


Index(
    "ix_courier_transports_transport_keyset",
    CourierTransport.transport_id,
    CourierTransport.created_at.desc(),
    CourierTransport.id.desc(),
)

Index(
    "ix_courier_transports_latest_rental",
    CourierTransport.transport_id,
    CourierTransport.started_at.desc(),
    CourierTransport.id.desc(),
)
