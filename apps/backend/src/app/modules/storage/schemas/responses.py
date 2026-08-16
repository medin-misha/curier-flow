"""Схемы ответов модуля storage.

`bucket` и `key` наружу не отдаются: клиенту они не нужны (доступ к объекту
даёт только подписанная ссылка), а раскладка бакета — внутреннее дело сервиса.
"""

from datetime import datetime
from uuid import UUID

from app.kernel.schemas import BaseResponse
from app.modules.storage.models import FileStatus


class UploadUrlResponse(BaseResponse):
    """Куда лить файл и с какими заголовками.

    `content_type` возвращается не для справки: ровно этот заголовок вшит в
    подпись, и с любым другим хранилище отвергнет PUT.
    """

    file_id: UUID
    upload_url: str
    content_type: str
    expires_in: int


class FileResponse(BaseResponse):
    """Метаданные файла.

    Не путать с `fastapi.responses.FileResponse`: отдавать содержимое файла
    через приложение модуль не умеет и не должен — этим занимается хранилище.
    """

    id: UUID
    original_name: str
    content_type: str
    size: int
    status: FileStatus
    etag: str | None
    owner_id: UUID | None
    created_at: datetime


class FileDetailResponse(FileResponse):
    """Метаданные файла и ссылка на скачивание.

    `download_url` заполнен только у `ready`: у `pending` объекта в хранилище
    может ещё не быть, и подписанная ссылка вела бы в никуда.
    """

    download_url: str | None
