"""Входящие контракты профиля курьера без импорта соседнего модуля."""

from typing import ClassVar
from uuid import UUID

from pydantic import AwareDatetime

from app.kernel.events.bus import DomainEvent


class CourierProfileChanged(DomainEvent):
    """Полный актуальный контакт после создания или изменения курьера."""

    topic: ClassVar[str] = "courier.profile_changed"

    courier_id: UUID
    full_name: str
    phone: str
    changed_at: AwareDatetime


class CourierDeleted(DomainEvent):
    """Факт удаления курьера; старые события больше не восстанавливают контакт."""

    topic: ClassVar[str] = "courier.deleted"

    courier_id: UUID
    changed_at: AwareDatetime
