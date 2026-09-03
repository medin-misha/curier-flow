"""CRUD и правила чеков компании."""

from typing import NoReturn
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, NotFound, ValidationFailed
from app.kernel.pagination import Page, PageParams
from app.modules.finance.models import Receipt, ReceiptTag
from app.modules.finance.schemas.requests import (
    ReceiptCreate,
    ReceiptPatch,
    ReceiptTagCreate,
    ReceiptTagPatch,
)
from app.platform.files import File, FileStatus, get_file


async def create_receipt(request: ReceiptCreate, *, session: AsyncSession) -> Receipt:
    """Создать чек для готового и ещё не занятого файла."""
    await _require_ready_file(request.file_id, session=session)
    if request.tag_id is not None:
        await _require_tag(request.tag_id, session=session)
    try:
        return await CRUD.create(Receipt, request, session)
    except IntegrityError as error:
        _raise_known_integrity(error)


async def get_receipt(receipt_id: UUID, *, session: AsyncSession) -> Receipt:
    """Вернуть чек по идентификатору."""
    return await CRUD.get_or_404(Receipt, receipt_id, session)


async def list_receipts(
    page: PageParams,
    *,
    session: AsyncSession,
    tag_id: UUID | None = None,
) -> Page[Receipt]:
    """Вернуть страницу чеков по keyset-курсору."""
    where = () if tag_id is None else (Receipt.tag_id == tag_id,)
    return await CRUD.list_page(Receipt, session, page=page, where=where)


async def patch_receipt(
    receipt_id: UUID,
    patch: ReceiptPatch,
    *,
    session: AsyncSession,
) -> Receipt:
    """Изменить присланные поля чека."""
    receipt = await CRUD.get_or_404(Receipt, receipt_id, session)
    if "file_id" in patch.model_fields_set:
        if patch.file_id is None:
            raise ValidationFailed("Receipt file is required", reason="file-required")
        await _require_ready_file(patch.file_id, session=session)
    if "tag_id" in patch.model_fields_set and patch.tag_id is not None:
        await _require_tag(patch.tag_id, session=session)
    try:
        return await CRUD.update(receipt, patch, session)
    except IntegrityError as error:
        _raise_known_integrity(error)


async def delete_receipt(receipt_id: UUID, *, session: AsyncSession) -> None:
    """Удалить чек, после чего его File снова можно удалить."""
    receipt = await CRUD.get_or_404(Receipt, receipt_id, session)
    await CRUD.delete(receipt, session)


async def create_tag(request: ReceiptTagCreate, *, session: AsyncSession) -> ReceiptTag:
    """Создать уникальный по имени тег расходов."""
    try:
        return await CRUD.create(ReceiptTag, request, session)
    except IntegrityError as error:
        _raise_known_integrity(error)


async def get_tag(tag_id: UUID, *, session: AsyncSession) -> ReceiptTag:
    """Вернуть тег расходов по идентификатору."""
    return await CRUD.get_or_404(ReceiptTag, tag_id, session)


async def list_tags(page: PageParams, *, session: AsyncSession) -> Page[ReceiptTag]:
    """Вернуть keyset-страницу тегов расходов."""
    return await CRUD.list_page(ReceiptTag, session, page=page)


async def patch_tag(
    tag_id: UUID,
    patch: ReceiptTagPatch,
    *,
    session: AsyncSession,
) -> ReceiptTag:
    """Переименовать тег расходов."""
    tag = await CRUD.get_or_404(ReceiptTag, tag_id, session)
    try:
        return await CRUD.update(tag, patch, session)
    except IntegrityError as error:
        _raise_known_integrity(error)


async def delete_tag(tag_id: UUID, *, session: AsyncSession) -> None:
    """Удалить тег и снять его со связанных чеков."""
    tag = await CRUD.get_or_404(ReceiptTag, tag_id, session)
    await session.execute(
        update(Receipt)
        .where(Receipt.tag_id == tag_id)
        .values(tag_id=None, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    await CRUD.delete(tag, session)


async def _require_ready_file(file_id: UUID, *, session: AsyncSession) -> File:
    """Заблокировать File и разрешить привязку только в состоянии ready."""
    file = await get_file(session, file_id, for_update=True)
    if file is None:
        raise NotFound("File not found", resource=File.__name__, pk=str(file_id))
    if file.status is not FileStatus.READY:
        raise ValidationFailed("Receipt file is not ready", reason="file-not-ready")
    return file


def _raise_known_integrity(error: IntegrityError) -> NoReturn:
    """Преобразовать известные ограничения finance в публичные ошибки."""
    constraint = _constraint_name(error)
    if constraint == "uq_receipts_file_id":
        raise Conflict(
            "File is already attached to a receipt", reason="receipt-file-in-use"
        ) from error
    if constraint == "receipt_file_not_ready":
        raise ValidationFailed("Receipt file is not ready", reason="file-not-ready") from error
    if constraint == "uq_receipt_tags_name_ci":
        raise Conflict(
            "Receipt tag name is already used", reason="receipt-tag-name-in-use"
        ) from error
    raise error


async def _require_tag(tag_id: UUID, *, session: AsyncSession) -> ReceiptTag:
    """Потребовать существующий тег расходов."""
    return await CRUD.get_or_404(ReceiptTag, tag_id, session)


def _constraint_name(error: IntegrityError) -> str | None:
    """Достать имя PostgreSQL constraint из цепочки asyncpg adapter."""
    original = error.orig
    candidates = (
        original,
        original.__cause__ if original is not None else None,
        original.__context__ if original is not None else None,
    )
    for candidate in candidates:
        if candidate is None:
            continue
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name
        diag = getattr(candidate, "diag", None)
        name = getattr(diag, "constraint_name", None)
        if isinstance(name, str):
            return name
    return None
