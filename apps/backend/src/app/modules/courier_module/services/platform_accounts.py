"""Создание и изменение platform accounts курьера."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict
from app.modules.courier_module.models import CourierPlatformAccount, PlatformAccountStatus
from app.modules.courier_module.schemas.requests import (
    CourierBulkStatusPatch,
    PlatformAccountCreate,
    PlatformAccountPatch,
)
from app.modules.courier_module.services.common import raise_known_integrity
from app.modules.courier_module.services.queries import (
    get_platform_account,
    lock_courier,
    lock_couriers,
)


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


async def bulk_patch_platform_status(
    request: CourierBulkStatusPatch,
    *,
    session: AsyncSession,
) -> int:
    """Проверить всю выборку и сменить статус только выбранной платформы."""
    courier_ids = await lock_couriers(request.courier_ids, session=session)
    accounts = (
        await session.scalars(
            select(CourierPlatformAccount)
            .where(
                CourierPlatformAccount.courier_id.in_(courier_ids),
                CourierPlatformAccount.platform == request.platform,
            )
            .order_by(CourierPlatformAccount.courier_id)
            .with_for_update()
        )
    ).all()
    missing = sorted(set(courier_ids) - {account.courier_id for account in accounts})
    if missing:
        raise Conflict(
            "Couriers do not have an account on this platform",
            reason="platform-account-missing",
            platform=request.platform.value,
            courier_ids=[str(courier_id) for courier_id in missing],
        )

    updated_count = 0
    for account in accounts:
        if account.status != request.status:
            account.status = request.status
            updated_count += 1
    await session.flush()
    return updated_count
