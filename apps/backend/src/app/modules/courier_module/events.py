"""Доменные события, владельцем которых является courier_module."""

from typing import ClassVar
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.kernel.events.bus import DomainEvent
from app.modules.courier_module.models import DeliveryPlatform


class CourierRegistered(DomainEvent):
    """Факт создания нового Courier вместе со всеми его платформами."""

    topic: ClassVar[str] = "courier.registered"

    courier_id: UUID
    full_name: str = Field(min_length=1, max_length=255)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    platforms: list[DeliveryPlatform] = Field(min_length=1, max_length=3)


class CourierProfileChanged(DomainEvent):
    """Полный контакт после создания или изменения профиля курьера."""

    topic: ClassVar[str] = "courier.profile_changed"

    courier_id: UUID
    full_name: str
    phone: str
    changed_at: AwareDatetime


class CourierDeleted(DomainEvent):
    """Факт удаления курьера для очистки внешних проекций."""

    topic: ClassVar[str] = "courier.deleted"

    courier_id: UUID
    changed_at: AwareDatetime
