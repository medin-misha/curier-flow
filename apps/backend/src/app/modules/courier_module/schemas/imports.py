"""Версионированный контракт переноса исторических курьеров без файлов."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.kernel.errors import ValidationFailed
from app.kernel.schemas import BaseRequest, BaseResponse
from app.modules.courier_module.models import DeliveryPlatform, PlatformAccountStatus
from app.modules.courier_module.schemas.requests import CourierProfileCreate
from app.modules.courier_module.services.common import normalize_email, normalize_phone


class ImportPlatformAccount(BaseRequest):
    platform: DeliveryPlatform
    status: PlatformAccountStatus


class CourierImportCreate(CourierProfileCreate):
    platform_accounts: list[ImportPlatformAccount] = Field(min_length=1, max_length=3)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _unique_platforms(self) -> Self:
        platforms = [account.platform for account in self.platform_accounts]
        if len(platforms) != len(set(platforms)):
            raise ValueError("platform_accounts must contain unique platforms")
        return self

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _validate_identity(value, phone=False)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return _validate_identity(value, phone=True)


def _validate_identity(value: str, *, phone: bool) -> str:
    try:
        return normalize_phone(value) if phone else normalize_email(value)
    except ValidationFailed as error:
        raise ValueError(error.detail) from error


class CourierImportRecord(BaseRequest):
    source_row: int = Field(ge=2)
    legacy_id: str = Field(min_length=1, max_length=128)
    courier: CourierImportCreate


class CourierImportBatch(BaseRequest):
    schema_version: Literal[1]
    couriers: list[CourierImportRecord] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _unique_sources(self) -> Self:
        rows = [record.source_row for record in self.couriers]
        ids = [record.legacy_id for record in self.couriers]
        if len(rows) != len(set(rows)) or len(ids) != len(set(ids)):
            raise ValueError("source_row and legacy_id must be unique")
        return self


class CourierImportResult(BaseResponse):
    source_row: int
    legacy_id: str
    outcome: Literal["created", "would_create", "existing", "conflict"]
    courier_id: UUID | None = None
    reason: str | None = None


class CourierImportResponse(BaseResponse):
    dry_run: bool
    created_count: int = 0
    would_create_count: int = 0
    existing_count: int = 0
    conflict_count: int = 0
    results: list[CourierImportResult]
