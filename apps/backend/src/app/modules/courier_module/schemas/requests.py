"""Входные схемы courier_module; server-owned File metadata отсутствуют."""

from datetime import UTC, date, datetime
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.kernel.schemas import BaseRequest
from app.modules.courier_module.models import (
    DeliveryPlatform,
    DocumentPurpose,
    DocumentType,
    PlatformAccountStatus,
)


def _future_date_of_birth(value: date | None) -> date | None:
    """Отвергнуть дату рождения из будущего."""
    if value is not None and value > datetime.now(tz=UTC).date():
        raise ValueError("date_of_birth must not be in the future")
    return value


def _aware_datetime(value: datetime | None) -> datetime | None:
    """Не принимать naive datetime для timestamptz-полей."""
    if value is not None and value.tzinfo is None:
        raise ValueError("datetime must include a timezone offset")
    return value


class PlatformAccountCreate(BaseRequest):
    """Платформа, на которой нужно завести pending account."""

    platform: DeliveryPlatform


class CourierDocumentCreate(BaseRequest):
    """Metadata одного загружаемого документа."""

    type: DocumentType
    purpose: DocumentPurpose
    legal_hold_until: datetime | None = None

    _validate_hold = field_validator("legal_hold_until")(_aware_datetime)


class CourierAggregateCreate(BaseRequest):
    """Courier, platform accounts и metadata multipart-документов."""

    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=320)
    phone: str = Field(min_length=1, max_length=32)
    date_of_birth: date
    city: str | None = Field(default=None, max_length=128)
    address: str | None = None
    citizenship: str | None = Field(default=None, max_length=128)
    bank_account: str | None = Field(default=None, max_length=64)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    consent_to_processing: bool = False
    platform_accounts: list[PlatformAccountCreate] = Field(min_length=1, max_length=3)
    documents: list[CourierDocumentCreate] = Field(default_factory=list)

    _validate_date_of_birth = field_validator("date_of_birth")(_future_date_of_birth)

    @model_validator(mode="after")
    def _platforms_are_unique(self) -> Self:
        """Одна platform может появиться в aggregate не больше одного раза."""
        platforms = [account.platform for account in self.platform_accounts]
        if len(platforms) != len(set(platforms)):
            raise ValueError("platform_accounts must contain unique platforms")
        return self


class CourierPatch(BaseRequest):
    """Частичное обновление scalar-полей Courier."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=1, max_length=320)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    date_of_birth: date | None = None
    city: str | None = Field(default=None, max_length=128)
    address: str | None = None
    citizenship: str | None = Field(default=None, max_length=128)
    bank_account: str | None = Field(default=None, max_length=64)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    consent_to_processing: bool | None = None

    _validate_date_of_birth = field_validator("date_of_birth")(_future_date_of_birth)

    @model_validator(mode="after")
    def _forbid_required_nulls(self) -> Self:
        """Отличить пропуск required-поля от попытки записать NULL."""
        required = {
            "full_name",
            "email",
            "phone",
            "date_of_birth",
            "consent_to_processing",
        }
        nulled = sorted(
            name for name in self.model_fields_set & required if getattr(self, name) is None
        )
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        return self


class CourierBulkRequest(BaseRequest):
    """Явная ограниченная выборка курьеров для атомарной операции."""

    courier_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("courier_ids")
    @classmethod
    def _unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("courier_ids must contain unique IDs")
        return value


class CourierBulkStatusPatch(CourierBulkRequest):
    """Единый статус регистраций выбранной платформы."""

    platform: DeliveryPlatform
    status: PlatformAccountStatus


class PlatformAccountPatch(BaseRequest):
    """Смена status одной platform-регистрации."""

    status: PlatformAccountStatus | None = None

    @model_validator(mode="after")
    def _forbid_status_null(self) -> Self:
        """Пропущенный status не меняет строку, explicit null запрещён."""
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Fields must not be null: status")
        return self


class CourierDocumentPatch(BaseRequest):
    """Частичное изменение metadata/hold документа."""

    type: DocumentType | None = None
    purpose: DocumentPurpose | None = None
    legal_hold_until: datetime | None = None

    _validate_hold = field_validator("legal_hold_until")(_aware_datetime)

    @model_validator(mode="after")
    def _forbid_required_nulls(self) -> Self:
        """Разрешить null только для nullable legal_hold_until."""
        nulled = sorted(
            name
            for name in self.model_fields_set & {"type", "purpose"}
            if getattr(self, name) is None
        )
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        return self
