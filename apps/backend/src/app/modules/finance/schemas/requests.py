"""Схемы создания и изменения чеков."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.kernel.schemas import BaseRequest

PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class ReceiptCreate(BaseRequest):
    """Новый чек компании."""

    file_id: UUID
    amount: PositiveMoney
    date: dt.date


class ReceiptPatch(BaseRequest):
    """Частичное изменение даты, файла или суммы чека."""

    file_id: UUID | None = None
    amount: PositiveMoney | None = None
    date: dt.date | None = None

    @model_validator(mode="after")
    def _forbid_explicit_nulls(self) -> Self:
        """Не разрешать очистку обязательных полей через explicit null."""
        nulled = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        return self
