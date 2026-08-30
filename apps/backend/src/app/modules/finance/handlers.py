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
from app.modules.finance.schemas.requests import ReceiptCreate, ReceiptPatch
from app.modules.finance.schemas.responses import ReceiptResponse
from app.modules.finance.services import (
    create_receipt,
    delete_receipt,
    get_receipt,
    list_receipts,
    patch_receipt,
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
async def list_page(page: PageQuery, session: RoSession) -> Page[ReceiptResponse]:
    """Отдать страницу чеков по keyset-курсору."""
    found = await list_receipts(page, session=session)
    return Page[ReceiptResponse](
        items=[ReceiptResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/{receipt_id}", summary="Receipt by id")
@authenticated
async def retrieve(receipt_id: UUID, session: RoSession) -> ReceiptResponse:
    """Отдать один чек."""
    return ReceiptResponse.model_validate(await get_receipt(receipt_id, session=session))


@router.patch("/{receipt_id}", summary="Update a receipt")
@authenticated
async def update(receipt_id: UUID, body: ReceiptPatch, uow: Uow) -> ReceiptResponse:
    """Изменить дату, файл или сумму чека."""
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
