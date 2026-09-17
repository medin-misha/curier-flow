"""Публичные проекции транспорта, комплектации, аренды и File."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import field_serializer

from app.kernel.schemas import BaseResponse
from app.modules.transport_module.models import RentalPaymentType


class FileResponse(BaseResponse):
    """Безопасные метаданные договора без bucket, key и owner."""

    id: UUID
    original_name: str
    content_type: str
    size: int
    status: str
    created_at: datetime


class CourierTransportResponse(BaseResponse):
    """Период аренды с вычисляемой активностью и договором."""

    id: UUID
    transport_id: UUID
    courier_id: UUID
    payment_type: RentalPaymentType | None
    started_at: datetime
    ended_at: datetime | None
    file_id: UUID | None
    file: FileResponse | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TransportComponentResponse(BaseResponse):
    """Позиция комплектации с вычисленной полной стоимостью."""

    id: UUID
    transport_id: UUID
    name: str
    unit_price: Decimal
    quantity: int
    total_price: Decimal
    created_at: datetime
    updated_at: datetime

    @field_serializer("unit_price", "total_price")
    def _serialize_money(self, value: Decimal) -> str:
        return format(value, ".2f")


class TransportListItemResponse(BaseResponse):
    """Транспорт в списке с признаком доступности."""

    id: UUID
    type: str
    model: str
    serial_number: str
    ordinal_number: int | None
    color: str
    deposit_required: bool
    deposit_amount: Decimal | None
    rental_price: Decimal
    is_available: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("deposit_amount", "rental_price")
    def _serialize_money(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".2f")


class TransportDetailResponse(TransportListItemResponse):
    """Транспорт, текущая комплектация и активная аренда."""

    components: list[TransportComponentResponse]
    active_rental: CourierTransportResponse | None
    comment: str | None
    debt_amount: Decimal

    @field_serializer("debt_amount")
    def _serialize_debt(self, value: Decimal) -> str:
        return format(value, ".2f")
