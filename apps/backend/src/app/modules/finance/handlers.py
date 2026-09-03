"""Защищённые HTTP-ручки чеков компании."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.idempotency import idempotent
from app.kernel.pagination import Page, PageParams
from app.kernel.security.authentication import authenticated
from app.modules.finance.schemas.requests import (
    ReceiptCreate,
    ReceiptPatch,
    ReceiptTagCreate,
    ReceiptTagPatch,
)
from app.modules.finance.schemas.responses import ReceiptResponse, ReceiptTagResponse
from app.modules.finance.services import (
    create_receipt,
    create_tag,
    delete_receipt,
    delete_tag,
    get_receipt,
    get_tag,
    list_receipts,
    list_tags,
    patch_receipt,
    patch_tag,
)

Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
PageQuery = Annotated[PageParams, Depends()]

router = APIRouter(tags=["finance"])


@router.post("", status_code=HTTPStatus.CREATED, summary="Create a receipt")
@authenticated
@idempotent
async def create(body: ReceiptCreate, uow: Uow) -> ReceiptResponse:
    """Создать чек."""
    return ReceiptResponse.model_validate(await create_receipt(body, session=uow))


@router.get("", summary="List receipts")
@authenticated
async def list_page(
    page: PageQuery,
    session: RoSession,
    tag_id: UUID | None = None,
) -> Page[ReceiptResponse]:
    """Отдать страницу чеков по keyset-курсору."""
    found = await list_receipts(page, session=session, tag_id=tag_id)
    return Page[ReceiptResponse](
        items=[ReceiptResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.post("/tags", status_code=HTTPStatus.CREATED, summary="Create a receipt tag")
@authenticated
@idempotent
async def create_receipt_tag(body: ReceiptTagCreate, uow: Uow) -> ReceiptTagResponse:
    """Создать тег расходов."""
    return ReceiptTagResponse.model_validate(await create_tag(body, session=uow))


@router.get("/tags", summary="List receipt tags")
@authenticated
async def list_receipt_tags(page: PageQuery, session: RoSession) -> Page[ReceiptTagResponse]:
    """Отдать страницу тегов расходов."""
    found = await list_tags(page, session=session)
    return Page[ReceiptTagResponse](
        items=[ReceiptTagResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/tags/{tag_id}", summary="Receipt tag by id")
@authenticated
async def retrieve_receipt_tag(tag_id: UUID, session: RoSession) -> ReceiptTagResponse:
    """Отдать тег расходов."""
    return ReceiptTagResponse.model_validate(await get_tag(tag_id, session=session))


@router.patch("/tags/{tag_id}", summary="Update a receipt tag")
@authenticated
async def update_receipt_tag(
    tag_id: UUID,
    body: ReceiptTagPatch,
    uow: Uow,
) -> ReceiptTagResponse:
    """Переименовать тег расходов."""
    return ReceiptTagResponse.model_validate(await patch_tag(tag_id, body, session=uow))


@router.delete(
    "/tags/{tag_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a receipt tag",
)
@authenticated
async def remove_receipt_tag(tag_id: UUID, uow: Uow) -> None:
    """Удалить тег расходов и снять его с чеков."""
    await delete_tag(tag_id, session=uow)


@router.get("/{receipt_id}", summary="Receipt by id")
@authenticated
async def retrieve(receipt_id: UUID, session: RoSession) -> ReceiptResponse:
    """Отдать один чек."""
    return ReceiptResponse.model_validate(await get_receipt(receipt_id, session=session))


@router.patch("/{receipt_id}", summary="Update a receipt")
@authenticated
async def update(receipt_id: UUID, body: ReceiptPatch, uow: Uow) -> ReceiptResponse:
    """Изменить дату, файл, сумму или тег чека."""
    return ReceiptResponse.model_validate(await patch_receipt(receipt_id, body, session=uow))


@router.delete(
    "/{receipt_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a receipt",
)
@authenticated
async def remove(receipt_id: UUID, uow: Uow) -> None:
    """Удалить чек."""
    await delete_receipt(receipt_id, session=uow)
