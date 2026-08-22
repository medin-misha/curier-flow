"""HTTP-разбор multipart/JSON и ответы courier_module."""

import asyncio
from collections.abc import Sequence
from http import HTTPStatus
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from fastapi import File as FormFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.db import session as db_session
from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.pagination import Page, PageParams
from app.modules.courier_module.schemas.requests import (
    CourierAggregateCreate,
    CourierDocumentCreate,
    CourierDocumentPatch,
    CourierPatch,
    PlatformAccountCreate,
    PlatformAccountPatch,
)
from app.modules.courier_module.schemas.responses import (
    CourierAggregateResponse,
    CourierDocumentWithFileResponse,
    PlatformAccountResponse,
)
from app.modules.courier_module.services import (
    DocumentUpload,
    courier_module_settings,
    create_courier_aggregate,
    create_courier_document,
    create_platform_account,
    delete_courier,
    delete_courier_document,
    get_courier,
    list_couriers,
    patch_courier,
    patch_courier_document,
    patch_platform_account,
)
from app.platform.files import MultipartUploader


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Отдать актуальную фабрику для aggregate-сервисов с явными границами."""
    return db_session.session_factory


async def get_courier_uploader(request: Request) -> MultipartUploader:
    """Достать долгоживущий uploader, созданный lifespan модуля."""
    return cast(MultipartUploader, request.app.state.courier_uploader)


Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
Uploader = Annotated[MultipartUploader, Depends(get_courier_uploader)]
PageQuery = Annotated[PageParams, Depends()]

router = APIRouter(tags=["courier"])


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Create a courier aggregate",
    responses={
        HTTPStatus.OK: {
            "model": CourierAggregateResponse,
            "description": "Existing aggregate matched by normalized email or phone",
        }
    },
)
async def create(
    payload: Annotated[str, Form()],
    response: Response,
    sessions: Sessions,
    uploader: Uploader,
    files: Annotated[list[UploadFile] | None, FormFile()] = None,
) -> CourierAggregateResponse:
    """Создать aggregate либо вернуть natural-key match без upload."""
    parts = files or []
    try:
        body = _parse_aggregate(payload)
    except RequestValidationError:
        await _close_http_uploads(parts)
        raise
    uploads = cast(Sequence[DocumentUpload], parts)
    result = await create_courier_aggregate(
        body,
        uploads,
        session_factory=sessions,
        uploader=uploader,
        settings=courier_module_settings,
    )
    response.status_code = HTTPStatus.CREATED if result.created else HTTPStatus.OK
    return CourierAggregateResponse.model_validate(result.courier)


@router.get("", summary="List courier aggregates")
async def list_page(
    page: PageQuery,
    session: RoSession,
    email: Annotated[str | None, Query(max_length=320)] = None,
    phone: Annotated[str | None, Query(max_length=32)] = None,
    full_name: Annotated[str | None, Query(max_length=255)] = None,
) -> Page[CourierAggregateResponse]:
    """Отдать keyset-страницу полных aggregates с точными фильтрами."""
    found = await list_couriers(
        page,
        session=session,
        email=email,
        phone=phone,
        full_name=full_name,
    )
    return Page[CourierAggregateResponse](
        items=[CourierAggregateResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/{courier_id}", summary="Courier aggregate by id")
async def retrieve(courier_id: UUID, session: RoSession) -> CourierAggregateResponse:
    """Отдать Courier с accounts и Documents/File."""
    return CourierAggregateResponse.model_validate(await get_courier(courier_id, session=session))


@router.patch("/{courier_id}", summary="Update courier fields")
async def update_courier(
    courier_id: UUID,
    body: CourierPatch,
    uow: Uow,
) -> CourierAggregateResponse:
    """Изменить только явно присланные scalar-поля Courier."""
    return CourierAggregateResponse.model_validate(
        await patch_courier(courier_id, body, session=uow)
    )


@router.delete(
    "/{courier_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a courier aggregate",
)
async def remove_courier(courier_id: UUID, uow: Uow) -> None:
    """Удалить aggregate и поставить все связанные Files на cleanup."""
    await delete_courier(courier_id, session=uow)


@router.post(
    "/{courier_id}/platform-accounts",
    status_code=HTTPStatus.CREATED,
    summary="Add a courier platform",
)
async def add_platform(
    courier_id: UUID,
    body: PlatformAccountCreate,
    uow: Uow,
) -> PlatformAccountResponse:
    """Добавить уникальную platform-регистрацию в pending."""
    return PlatformAccountResponse.model_validate(
        await create_platform_account(courier_id, body, session=uow)
    )


@router.patch(
    "/{courier_id}/platform-accounts/{account_id}",
    summary="Update a courier platform account",
)
async def update_platform(
    courier_id: UUID,
    account_id: UUID,
    body: PlatformAccountPatch,
    uow: Uow,
) -> PlatformAccountResponse:
    """Сменить status вложенной platform-регистрации."""
    return PlatformAccountResponse.model_validate(
        await patch_platform_account(courier_id, account_id, body, session=uow)
    )


@router.post(
    "/{courier_id}/documents",
    status_code=HTTPStatus.CREATED,
    summary="Upload a courier document",
)
async def add_document(
    courier_id: UUID,
    payload: Annotated[str, Form()],
    file: Annotated[UploadFile, FormFile()],
    sessions: Sessions,
    uploader: Uploader,
) -> CourierDocumentWithFileResponse:
    """Потоково загрузить File и атомарно добавить Document."""
    try:
        body = _parse_document(payload)
    except RequestValidationError:
        await _close_http_uploads([file])
        raise
    document = await create_courier_document(
        courier_id,
        body,
        cast(DocumentUpload, file),
        session_factory=sessions,
        uploader=uploader,
        settings=courier_module_settings,
    )
    return CourierDocumentWithFileResponse.model_validate(document)


@router.patch(
    "/{courier_id}/documents/{document_id}",
    summary="Update courier document metadata",
)
async def update_document(
    courier_id: UUID,
    document_id: UUID,
    body: CourierDocumentPatch,
    uow: Uow,
) -> CourierDocumentWithFileResponse:
    """Изменить type, purpose или legal hold вложенного документа."""
    return CourierDocumentWithFileResponse.model_validate(
        await patch_courier_document(courier_id, document_id, body, session=uow)
    )


@router.delete(
    "/{courier_id}/documents/{document_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a courier document",
)
async def remove_document(courier_id: UUID, document_id: UUID, uow: Uow) -> None:
    """Удалить Document и пометить его File к фоновой очистке."""
    await delete_courier_document(courier_id, document_id, session=uow)


def _parse_aggregate(payload: str) -> CourierAggregateCreate:
    """Разобрать JSON form-part и сохранить единый RFC 9457 validation flow."""
    try:
        return CourierAggregateCreate.model_validate_json(payload)
    except ValidationError as error:
        raise RequestValidationError(_payload_errors(error)) from error


def _parse_document(payload: str) -> CourierDocumentCreate:
    """Разобрать metadata JSON одного multipart-документа."""
    try:
        return CourierDocumentCreate.model_validate_json(payload)
    except ValidationError as error:
        raise RequestValidationError(_payload_errors(error)) from error


def _payload_errors(error: ValidationError) -> list[dict[str, object]]:
    """Добавить form-part payload к pydantic locations."""
    return [
        {
            **item,
            "loc": ("body", "payload", *item["loc"]),
        }
        for item in error.errors()
    ]


async def _close_http_uploads(files: Sequence[UploadFile]) -> None:
    """Закрыть multipart parts, если JSON payload отвергнут до сервиса."""
    await asyncio.gather(*(file.close() for file in files), return_exceptions=True)
