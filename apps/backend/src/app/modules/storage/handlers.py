"""HTTP-ручки модуля storage: двухфазная загрузка и жизненный цикл файла."""

from http import HTTPStatus
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.db import session as db_session
from app.kernel.pagination import Page, PageParams
from app.kernel.security.authentication import authenticated
from app.modules.storage.schemas.requests import ConfirmRequest, UploadUrlRequest
from app.modules.storage.schemas.responses import (
    FileDetailResponse,
    FileResponse,
    UploadUrlResponse,
)
from app.modules.storage.services import (
    FileStorage,
    confirm_upload,
    create_upload,
    get_file,
    list_files,
    mark_for_deletion,
)


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Отдать фабрику сессий процесса.

    Не `get_uow` и не `get_ro_session`: границы транзакций в этом модуле
    держит сервис. Каждая его операция сочетает базу и объектное хранилище, а
    поход в хранилище внутри открытой транзакции запрещён — подробности в
    докстринге `services.py`.

    Фабрика читается из модуля в момент запроса, а не импортируется по имени:
    тесты подменяют глобаль ядра, и связанное на импорте имя указывало бы на
    прежнюю фабрику до конца процесса.
    """
    return db_session.session_factory


async def get_file_storage(request: Request) -> FileStorage:
    """Достать клиент хранилища и лимиты, созданные lifespan модуля.

    `cast` неизбежен: `app.state` не типизирован, а без него mypy видит `Any`.
    Ключ кладёт `module.py` — единственное место, где клиент создаётся.
    """
    return cast(FileStorage, request.app.state.file_storage)


#: Псевдонимы объявлены здесь, а не взяты из `app.api.deps`: правило
#: зависимостей `api → modules → platform → kernel` запрещает модулю
#: импортировать слой api.
Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
Storage = Annotated[FileStorage, Depends(get_file_storage)]
PageQuery = Annotated[PageParams, Depends()]

router = APIRouter(tags=["files"])


@router.post("/upload-url", status_code=HTTPStatus.CREATED, summary="Issue an upload URL")
@authenticated
async def upload_url(
    body: UploadUrlRequest,
    sessions: Sessions,
    storage: Storage,
) -> UploadUrlResponse:
    """Создать запись о файле и выдать подписанную ссылку на загрузку."""
    ticket = await create_upload(body, session_factory=sessions, storage=storage)
    return UploadUrlResponse(
        file_id=ticket.file.id,
        upload_url=ticket.upload_url,
        content_type=ticket.file.content_type,
        expires_in=ticket.expires_in,
    )


@router.post("/{file_id}/confirm", summary="Confirm an uploaded file")
@authenticated
async def confirm(
    file_id: UUID,
    body: ConfirmRequest,
    sessions: Sessions,
    storage: Storage,
) -> FileResponse:
    """Проверить загруженный объект и перевести файл в `ready`."""
    file = await confirm_upload(file_id, body, session_factory=sessions, storage=storage)
    return FileResponse.model_validate(file)


@router.get("", summary="List files")
@authenticated
async def list_page(page: PageQuery, sessions: Sessions) -> Page[FileResponse]:
    """Отдать страницу файлов по keyset-курсору."""
    found = await list_files(page, session_factory=sessions)
    return Page[FileResponse](
        items=[FileResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/{file_id}", summary="File metadata and a download link")
@authenticated
async def retrieve(file_id: UUID, sessions: Sessions, storage: Storage) -> FileDetailResponse:
    """Отдать метаданные файла и ссылку на скачивание, если он готов."""
    link = await get_file(file_id, session_factory=sessions, storage=storage)
    return FileDetailResponse(
        **FileResponse.model_validate(link.file).model_dump(),
        download_url=link.download_url,
    )


@router.delete("/{file_id}", status_code=HTTPStatus.NO_CONTENT, summary="Delete a file")
@authenticated
async def remove(file_id: UUID, sessions: Sessions) -> None:
    """Пометить файл к удалению; объект уберёт периодическая задача."""
    await mark_for_deletion(file_id, session_factory=sessions)
