"""Схемы запросов и ответов для тестовых моделей."""

from datetime import datetime
from uuid import UUID

from app.kernel.schemas import BaseRequest, BaseResponse


class WidgetCreate(BaseRequest):
    """Поля, которые вправе задать клиент. `owner` выставляет сервер."""

    name: str
    quantity: int = 0


class WidgetPatch(BaseRequest):
    """Частичное обновление: незаданные поля не должны попадать в UPDATE."""

    name: str | None = None
    quantity: int | None = None
    owner: str | None = None
    deleted_at: datetime | None = None


class BlobCreate(BaseRequest):
    """Полезная нагрузка сущности без временных меток."""

    payload: str


class WidgetResponse(BaseResponse):
    """Ответ ручки: по нему проверяется, что повтор вернул то же самое."""

    id: UUID
    name: str
    quantity: int
    owner: str
