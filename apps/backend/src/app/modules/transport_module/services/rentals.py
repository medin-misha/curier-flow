"""Создание, завершение и подписание аренды."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, NotFound, ValidationFailed
from app.kernel.pagination import Page, PageParams
from app.modules.transport_module.models import CourierTransport
from app.modules.transport_module.schemas.requests import (
    CourierTransportClose,
    CourierTransportContractAttach,
    CourierTransportCreate,
)
from app.modules.transport_module.services.common import raise_known_integrity
from app.modules.transport_module.services.queries import (
    get_rental,
    lock_transport,
    require_transport,
)
from app.platform.files import File, FileStatus, get_file


async def create_rental(
    transport_id: UUID,
    request: CourierTransportCreate,
    *,
    session: AsyncSession,
) -> CourierTransport:
    """Создать активную или завершённую аренду под DB-защитой пересечений."""
    await lock_transport(transport_id, session=session)
    _validate_period(request.started_at, request.ended_at)
    if request.file_id is not None:
        await _require_ready_file(request.file_id, session=session)
    try:
        rental = await CRUD.create(CourierTransport, request, session, transport_id=transport_id)
    except IntegrityError as error:
        raise_known_integrity(error)
    return await get_rental(transport_id, rental.id, session=session)


async def list_rentals(
    transport_id: UUID,
    page: PageParams,
    *,
    session: AsyncSession,
) -> Page[CourierTransport]:
    """Вернуть parent-scoped keyset-историю аренды."""
    await require_transport(transport_id, session=session)
    return await CRUD.list_page(
        CourierTransport,
        session,
        page=page,
        where=(CourierTransport.transport_id == transport_id,),
    )


async def close_rental(
    transport_id: UUID,
    rental_id: UUID,
    request: CourierTransportClose,
    *,
    session: AsyncSession,
) -> CourierTransport:
    """Завершить только активную аренду один раз."""
    rental = await get_rental(
        transport_id,
        rental_id,
        session=session,
        for_update=True,
    )
    if rental.ended_at is not None:
        raise Conflict("Rental is already closed", reason="rental-already-closed")
    _validate_period(rental.started_at, request.ended_at)
    rental.ended_at = request.ended_at
    await session.flush()
    return await get_rental(transport_id, rental_id, session=session)


async def attach_contract(
    transport_id: UUID,
    rental_id: UUID,
    request: CourierTransportContractAttach,
    *,
    session: AsyncSession,
) -> CourierTransport:
    """Необратимо приложить готовый File к аренде."""
    rental = await get_rental(
        transport_id,
        rental_id,
        session=session,
        for_update=True,
    )
    if rental.file_id is not None:
        raise Conflict("Rental already has a signed contract", reason="contract-already-attached")
    await _require_ready_file(request.file_id, session=session)
    rental.file_id = request.file_id
    try:
        await session.flush()
    except IntegrityError as error:
        raise_known_integrity(error)
    return await get_rental(transport_id, rental_id, session=session)


async def _require_ready_file(file_id: UUID, *, session: AsyncSession) -> File:
    """Заблокировать File и разрешить только состояние ready."""
    file = await get_file(session, file_id, for_update=True)
    if file is None:
        raise NotFound("File not found", resource=File.__name__, pk=str(file_id))
    if file.status is not FileStatus.READY:
        raise ValidationFailed("Contract file is not ready", reason="file-not-ready")
    return file


def _validate_period(started_at: datetime, ended_at: datetime | None) -> None:
    """Повторить временные правила на сервисной границе."""
    now = datetime.now(tz=UTC)
    if started_at.tzinfo is None or (ended_at is not None and ended_at.tzinfo is None):
        raise ValidationFailed("Rental dates must be timezone-aware", reason="naive-rental-date")
    if started_at > now or (ended_at is not None and ended_at > now):
        raise ValidationFailed(
            "Rental dates must not be in the future", reason="future-rental-date"
        )
    if ended_at is not None and ended_at <= started_at:
        raise ValidationFailed(
            "ended_at must be later than started_at", reason="invalid-rental-period"
        )
