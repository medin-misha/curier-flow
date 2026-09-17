"""Строгие схемы создания и команд transport_module."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.kernel.schemas import BaseRequest
from app.modules.transport_module.models import RentalPaymentType

TransportType = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=64),
]
Trimmed128 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Trimmed64 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
TransportComment = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]
SerialNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=64),
]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
OrdinalNumber = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]


class TransportCreate(BaseRequest):
    """Новый транспорт и текущие условия аренды."""

    type: TransportType
    model: Trimmed128
    serial_number: SerialNumber
    ordinal_number: OrdinalNumber | None = None
    color: Trimmed64
    deposit_required: bool = False
    deposit_amount: PositiveMoney | None = None
    rental_price: PositiveMoney
    comment: TransportComment | None = None
    debt_amount: NonNegativeMoney = Decimal("0.00")

    @model_validator(mode="after")
    def _validate_deposit(self) -> Self:
        if self.deposit_required != (self.deposit_amount is not None):
            raise ValueError("deposit_amount is required exactly when deposit_required is true")
        return self


class TransportPatch(BaseRequest):
    """Частичное изменение транспорта с очисткой комментария и порядкового номера."""

    type: TransportType | None = None
    model: Trimmed128 | None = None
    serial_number: SerialNumber | None = None
    ordinal_number: OrdinalNumber | None = None
    color: Trimmed64 | None = None
    deposit_required: bool | None = None
    deposit_amount: PositiveMoney | None = None
    rental_price: PositiveMoney | None = None
    comment: TransportComment | None = None
    debt_amount: NonNegativeMoney | None = None

    @model_validator(mode="after")
    def _forbid_explicit_nulls(self) -> Self:
        nulled = sorted(
            name
            for name in self.model_fields_set
            if name not in {"comment", "ordinal_number"} and getattr(self, name) is None
        )
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        if {
            "deposit_required",
            "deposit_amount",
        } <= self.model_fields_set and self.deposit_required is False:
            raise ValueError("deposit_amount cannot be sent when deposit_required is false")
        return self


class TransportComponentCreate(BaseRequest):
    """Новая позиция текущей комплектации."""

    name: Trimmed128
    unit_price: NonNegativeMoney
    quantity: int = Field(gt=0)


class TransportComponentPatch(BaseRequest):
    """Частичное изменение позиции комплектации без explicit null."""

    name: Trimmed128 | None = None
    unit_price: NonNegativeMoney | None = None
    quantity: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _forbid_explicit_nulls(self) -> Self:
        nulled = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        return self


class CourierTransportCreate(BaseRequest):
    """Активная или завершённая историческая аренда."""

    courier_id: UUID
    payment_type: RentalPaymentType
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    file_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_period(self) -> Self:
        now = datetime.now(tz=UTC)
        if self.started_at > now or (self.ended_at is not None and self.ended_at > now):
            raise ValueError("Rental dates must not be in the future")
        if self.ended_at is not None and self.ended_at <= self.started_at:
            raise ValueError("ended_at must be later than started_at")
        return self


class CourierTransportPaymentPatch(BaseRequest):
    """Указать или изменить только тип оплаты существующей аренды."""

    payment_type: RentalPaymentType


class CourierTransportClose(BaseRequest):
    """Фактическая дата завершения; команда закрывает аренду сразу."""

    ended_at: AwareDatetime


class CourierTransportContractAttach(BaseRequest):
    """Неизменяемая ссылка на готовый подписанный договор."""

    file_id: UUID
