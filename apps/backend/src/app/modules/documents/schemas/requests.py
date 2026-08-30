"""Запросы создания шаблона и генерации документа."""

from typing import Annotated
from uuid import UUID

from pydantic import Field, StrictStr, StringConstraints

from app.kernel.schemas import BaseRequest

TemplateName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class DocumentTemplateCreate(BaseRequest):
    """Новый шаблон из уже подтверждённого File."""

    name: TemplateName
    file_id: UUID


class DocumentRenderRequest(BaseRequest):
    """Строковые значения, сгруппированные как placeholders шаблона."""

    values: dict[str, dict[str, StrictStr]] = Field(min_length=1)
