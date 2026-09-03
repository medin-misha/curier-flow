"""Схемы ответов модуля finance."""

import datetime as dt
from decimal import Decimal
from uuid import UUID

from pydantic import field_serializer

from app.kernel.schemas import BaseResponse


class ReceiptResponse(BaseResponse):
    """Чек компании."""

    id: UUID
    file_id: UUID
    tag_id: UUID | None
    amount: Decimal
    date: dt.date
    created_at: dt.datetime
    updated_at: dt.datetime

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> str:
        """Сериализовать деньги без потери точности через float."""
        return format(value, ".2f")


class ReceiptTagResponse(BaseResponse):
    """Тег типа расхода."""

    id: UUID
    name: str
    created_at: dt.datetime
    updated_at: dt.datetime
