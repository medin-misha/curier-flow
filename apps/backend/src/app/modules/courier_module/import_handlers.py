"""HTTP-контракт импорта; вся обработка записей остаётся в сервисе."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.session import get_uow
from app.kernel.security.authentication import authenticated
from app.modules.courier_module.schemas.imports import CourierImportBatch, CourierImportResponse
from app.modules.courier_module.services.imports import import_couriers

router = APIRouter(tags=["courier"])
Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]


@router.post("/import-courier", summary="Проверить или импортировать исторических курьеров")
@authenticated
async def import_batch(
    body: CourierImportBatch,
    session: Uow,
    dry_run: Annotated[bool, Query()] = True,
) -> CourierImportResponse:
    return await import_couriers(body, dry_run=dry_run, session=session)
