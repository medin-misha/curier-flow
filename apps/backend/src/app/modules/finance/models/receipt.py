"""Таблица `receipts`: чеки компании."""

import datetime as dt
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class Receipt(UUIDPkMixin, TimestampMixin, Base):
    """Чек с датой, суммой и ссылкой на загруженный файл."""

    __tablename__ = "receipts"
    __patchable__ = frozenset({"file_id", "amount", "date"})
    __table_args__ = (
        UniqueConstraint("file_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    date: Mapped[dt.date]


Index("ix_receipts_keyset", Receipt.created_at.desc(), Receipt.id.desc())
