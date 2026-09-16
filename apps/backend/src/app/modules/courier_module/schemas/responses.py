"""Полные aggregate-ответы courier_module без внутренних bucket/key."""

from datetime import date, datetime
from uuid import UUID

from app.kernel.schemas import BaseResponse
from app.modules.courier_module.models import (
    DeliveryPlatform,
    DocumentPurpose,
    DocumentType,
    PlatformAccountStatus,
)
from app.platform.files import FileStatus


class CourierBulkDeleteResponse(BaseResponse):
    """Число удалённых курьеров; очистка S3 выполняется отдельно."""

    deleted_count: int


class CourierBulkStatusResponse(BaseResponse):
    """Число изменённых регистраций и регистраций с уже нужным статусом."""

    updated_count: int
    unchanged_count: int


class FileResponse(BaseResponse):
    """Безопасная наружная часть общей File metadata."""

    id: UUID
    original_name: str
    content_type: str
    size: int
    status: FileStatus
    etag: str | None
    owner_id: UUID | None
    created_at: datetime


class PlatformAccountResponse(BaseResponse):
    """Регистрация Courier на delivery-платформе."""

    id: UUID
    courier_id: UUID
    platform: DeliveryPlatform
    status: PlatformAccountStatus
    created_at: datetime
    updated_at: datetime


class CourierDocumentWithFileResponse(BaseResponse):
    """Metadata документа со вложенным File, которому он принадлежит."""

    id: UUID
    courier_id: UUID
    file_id: UUID
    type: DocumentType
    purpose: DocumentPurpose
    legal_hold_until: datetime | None
    file: FileResponse
    created_at: datetime
    updated_at: datetime


class CourierAggregateResponse(BaseResponse):
    """Корень Courier и все доступные связанные данные."""

    id: UUID
    full_name: str
    email: str
    phone: str
    date_of_birth: date
    city: str | None
    address: str | None
    citizenship: str | None
    bank_account: str | None
    contact_platform: str | None
    contact: str | None
    source: str | None
    consent_to_processing: bool
    consent_at: datetime | None
    platform_accounts: list[PlatformAccountResponse]
    documents: list[CourierDocumentWithFileResponse]
    created_at: datetime
    updated_at: datetime
