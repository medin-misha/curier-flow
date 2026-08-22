"""Доменные контракты общей файловой подсистемы."""

from typing import ClassVar
from uuid import UUID

from app.kernel.events.bus import DomainEvent


class FileConfirmed(DomainEvent):
    """Факт готовности проверенного файла, атомарный со статусом ready."""

    topic: ClassVar[str] = "file.confirmed"

    file_id: UUID
    bucket: str
    key: str
    original_name: str
    content_type: str
    size: int
    owner_id: UUID | None
