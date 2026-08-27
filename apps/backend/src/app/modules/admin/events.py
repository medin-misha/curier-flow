"""Событийные контракты административного модуля."""

from enum import StrEnum
from typing import ClassVar, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.kernel.events.bus import DomainEvent


class DeliveryPlatform(StrEnum):
    """Локальная проекция поддерживаемых courier-платформ."""

    BOLT_FOOD = "bolt_food"
    FOODORA = "foodora"
    WOLT = "wolt"


class CourierRegistered(DomainEvent):
    """Нужная admin-модулю проекция чужого факта регистрации Courier."""

    topic: ClassVar[str] = "courier.registered"

    courier_id: UUID
    full_name: str = Field(min_length=1, max_length=255)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    platforms: list[DeliveryPlatform] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def platforms_are_unique(self) -> Self:
        """Не принимать повреждённый межмодульный контракт с дублями."""
        if len(set(self.platforms)) != len(self.platforms):
            raise ValueError("platforms must be unique")
        return self


class CourierRegistrationTelegramNotificationCreated(DomainEvent):
    """Факт подготовки одного Telegram-уведомления для одного Admin."""

    topic: ClassVar[str] = "courier.registration.telegram_notification.created"

    telegram_id: int = Field(gt=0, le=2**63 - 1)
    full_name: str = Field(min_length=1, max_length=255)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    platform: DeliveryPlatform
