"""Таблица `transports`: транспорт и условия его аренды."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.modules.transport_module.models.component import TransportComponent
    from app.modules.transport_module.models.courier_transport import CourierTransport


class Transport(UUIDPkMixin, TimestampMixin, Base):
    """Транспорт с нормализованным серийным номером и текущей комплектацией."""

    __tablename__ = "transports"
    __patchable__ = frozenset(
        {
            "type",
            "model",
            "serial_number",
            "color",
            "deposit_required",
            "deposit_amount",
            "rental_price",
            "comment",
            "debt_amount",
        }
    )
    __table_args__ = (
        UniqueConstraint("serial_number"),
        CheckConstraint(
            "char_length(type) > 0 AND type = lower(btrim(type))", name="type_normalized"
        ),
        CheckConstraint(
            "char_length(btrim(model)) > 0 AND model = btrim(model)", name="model_trimmed"
        ),
        CheckConstraint(
            "char_length(serial_number) > 0 AND serial_number = upper(btrim(serial_number))",
            name="serial_number_normalized",
        ),
        CheckConstraint(
            "char_length(btrim(color)) > 0 AND color = btrim(color)", name="color_trimmed"
        ),
        CheckConstraint("rental_price > 0", name="rental_price_positive"),
        CheckConstraint("debt_amount >= 0", name="debt_amount_non_negative"),
        CheckConstraint(
            "comment IS NULL OR (char_length(comment) <= 2000 AND "
            "char_length(btrim(comment)) > 0 AND comment = btrim(comment))",
            name="comment_normalized",
        ),
        CheckConstraint(
            "(deposit_required IS FALSE AND deposit_amount IS NULL) OR "
            "(deposit_required IS TRUE AND deposit_amount > 0)",
            name="deposit_state",
        ),
    )

    type: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    serial_number: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(64))
    deposit_required: Mapped[bool] = mapped_column(Boolean, default=False)
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    rental_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    debt_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    components: Mapped[list["TransportComponent"]] = relationship(
        back_populates="transport",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    rentals: Mapped[list["CourierTransport"]] = relationship(
        back_populates="transport",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    @property
    def active_rental(self) -> "CourierTransport | None":
        """Вернуть загруженную активную аренду транспорта."""
        return next((rental for rental in self.rentals if rental.ended_at is None), None)

    @property
    def is_available(self) -> bool:
        """Показать отсутствие активной аренды."""
        return self.active_rental is None


Index("ix_transports_keyset", Transport.created_at.desc(), Transport.id.desc())
