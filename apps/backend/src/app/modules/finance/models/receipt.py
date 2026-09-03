"""Таблица `receipts`: чеки компании."""

import datetime as dt
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class ReceiptTag(UUIDPkMixin, TimestampMixin, Base):
    """Переиспользуемый тип расхода для чеков."""

    __tablename__ = "receipt_tags"
    __patchable__ = frozenset({"name"})
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0 AND name = btrim(name)", name="name_trimmed"),
    )

    name: Mapped[str] = mapped_column(String(64))


class Receipt(UUIDPkMixin, TimestampMixin, Base):
    """Чек с датой, суммой и ссылкой на загруженный файл."""

    __tablename__ = "receipts"
    __patchable__ = frozenset({"file_id", "amount", "date", "tag_id"})
    __table_args__ = (
        UniqueConstraint("file_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    tag_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("receipt_tags.id", ondelete="SET NULL"),
        default=None,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    date: Mapped[dt.date]


Index("ix_receipts_keyset", Receipt.created_at.desc(), Receipt.id.desc())
Index(
    "ix_receipts_tag_keyset",
    Receipt.tag_id,
    Receipt.created_at.desc(),
    Receipt.id.desc(),
)
Index("ix_receipt_tags_keyset", ReceiptTag.created_at.desc(), ReceiptTag.id.desc())
Index("uq_receipt_tags_name_ci", func.lower(ReceiptTag.name), unique=True)
