"""Схемы запросов модуля storage.

В схемах нет ни `bucket`, ни `key`, ни `status`, ни `owner_id`: всё это
определяет сервер и передаёт в `CRUD.create` через `**overrides`. Клиент,
который смог бы задать ключ, перезаписал бы чужой объект.
"""

from pydantic import Field

from app.kernel.schemas import BaseRequest


class UploadUrlRequest(BaseRequest):
    """Заявка на загрузку: что клиент собирается залить.

    Размер заявляется заранее, чтобы отказ по лимиту случился до передачи
    файла, а не после. Фактический размер сервер всё равно проверит сам при
    подтверждении: заявке клиента верить нельзя.
    """

    original_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class ConfirmRequest(BaseRequest):
    """Подтверждение загрузки: ETag, который вернуло хранилище на PUT."""

    etag: str = Field(min_length=1, max_length=128)
