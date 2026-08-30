"""Таблица `transport_components`: текущая комплектация транспорта."""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.modules.transport_module.models.transport import Transport


class TransportComponent(UUIDPkMixin, TimestampMixin, Base):
    """Позиция текущей комплектации с количеством и ценой единицы."""

    __tablename__ = "transport_components"
    __patchable__ = frozenset({"name", "unit_price", "quantity"})
    __table_args__ = (
        UniqueConstraint("transport_id", "name"),
        CheckConstraint("char_length(btrim(name)) > 0 AND name = btrim(name)", name="name_trimmed"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    transport_id: Mapped[UUID] = mapped_column(ForeignKey("transports.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)

    transport: Mapped["Transport"] = relationship(back_populates="components")

    @property
    def total_price(self) -> Decimal:
        """Вычислить стоимость всей позиции без хранения производного поля."""
        return self.unit_price * self.quantity


Index(
    "ix_transport_components_transport_keyset",
    TransportComponent.transport_id,
    TransportComponent.created_at.desc(),
    TransportComponent.id.desc(),
)
