"""Доменные события модуля storage."""

from typing import ClassVar
from uuid import UUID

from app.kernel.events.bus import DomainEvent


class FileConfirmed(DomainEvent):
    """Файл загружен клиентом и проверен сервером.

    Событие несёт `bucket` и `key`, а не только идентификатор: потребитель
    (сборщик превью, антивирус, индексатор) должен уметь взять объект, не
    обращаясь к владельцу таблицы, — иначе модули снова начинают знать друг
    о друге.
    """

    topic: ClassVar[str] = "file.confirmed"

    file_id: UUID
    bucket: str
    key: str
    original_name: str
    content_type: str
    size: int
    owner_id: UUID | None
