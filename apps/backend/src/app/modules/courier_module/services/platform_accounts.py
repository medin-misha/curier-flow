"""Создание и изменение platform accounts курьера."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.modules.courier_module.models import CourierPlatformAccount, PlatformAccountStatus
from app.modules.courier_module.schemas.requests import (
    PlatformAccountCreate,
    PlatformAccountPatch,
)
from app.modules.courier_module.services.common import raise_known_integrity
from app.modules.courier_module.services.queries import get_platform_account, lock_courier


async def create_platform_account(
    courier_id: UUID,
    request: PlatformAccountCreate,
    *,
    session: AsyncSession,
) -> CourierPlatformAccount:
    """Добавить курьеру новую уникальную delivery-платформу."""
    await lock_courier(courier_id, session=session)
    account = CourierPlatformAccount(
        courier_id=courier_id,
        platform=request.platform,
        status=PlatformAccountStatus.PENDING,
    )
    session.add(account)
    try:
        await session.flush()
    except IntegrityError as error:
        raise_known_integrity(error)
    return account


async def patch_platform_account(
    courier_id: UUID,
    account_id: UUID,
    patch: PlatformAccountPatch,
    *,
    session: AsyncSession,
) -> CourierPlatformAccount:
    """Сменить status вложенного account только внутри заданного Courier."""
    account = await get_platform_account(courier_id, account_id, session=session)
    return await CRUD.update(account, patch, session)
