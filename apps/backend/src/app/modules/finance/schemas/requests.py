"""Схемы создания и изменения чеков."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.kernel.schemas import BaseRequest

PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class ReceiptTagCreate(BaseRequest):
    """Новый тег расходов."""

    name: TagName


class ReceiptTagPatch(BaseRequest):
    """Изменение названия тега расходов."""

    name: TagName | None = None

    @model_validator(mode="after")
    def _forbid_explicit_null(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Field must not be null: name")
        return self


class ReceiptCreate(BaseRequest):
    """Новый чек компании."""

    file_id: UUID
    amount: PositiveMoney
    date: dt.date
    tag_id: UUID | None = None


class ReceiptPatch(BaseRequest):
    """Частичное изменение даты, файла или суммы чека."""

    file_id: UUID | None = None
    amount: PositiveMoney | None = None
    date: dt.date | None = None
    tag_id: UUID | None = None

    @model_validator(mode="after")
    def _forbid_explicit_nulls(self) -> Self:
        """Не разрешать очистку обязательных полей через explicit null."""
        nulled = sorted(
            name
            for name in self.model_fields_set
            if name != "tag_id" and getattr(self, name) is None
        )
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        return self
