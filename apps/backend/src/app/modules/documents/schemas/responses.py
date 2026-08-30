"""Ответы модуля documents."""

from datetime import datetime
from uuid import UUID

from app.kernel.schemas import BaseResponse


class DocumentTemplateResponse(BaseResponse):
    """Сохранённый шаблон и извлечённая схема значений."""

    id: UUID
    name: str
    file_id: UUID
    fields: dict[str, list[str]]
    created_at: datetime
    updated_at: datetime
