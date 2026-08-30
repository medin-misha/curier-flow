"""Parent-scoped запросы транспорта и вложенных ресурсов."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.base import ExecutableOption

from app.kernel.errors import NotFound
from app.modules.transport_module.models import CourierTransport, Transport, TransportComponent


def active_rental_option() -> ExecutableOption:
    """Явно загрузить только текущую аренду вместе с File."""
    return selectinload(Transport.rentals.and_(CourierTransport.ended_at.is_(None))).joinedload(
        CourierTransport.file
    )


async def get_transport(transport_id: UUID, *, session: AsyncSession) -> Transport:
    """Вернуть транспорт с комплектацией и активной арендой."""
    transport = await session.scalar(
        select(Transport)
        .where(Transport.id == transport_id)
        .options(selectinload(Transport.components), active_rental_option())
        .execution_options(populate_existing=True)
    )
    if transport is None:
        raise NotFound("Transport not found", resource=Transport.__name__, pk=str(transport_id))
    return transport


async def require_transport(transport_id: UUID, *, session: AsyncSession) -> Transport:
    """Проверить существование parent без загрузки aggregate."""
    transport = await session.get(Transport, transport_id)
    if transport is None:
        raise NotFound("Transport not found", resource=Transport.__name__, pk=str(transport_id))
    return transport


async def lock_transport(transport_id: UUID, *, session: AsyncSession) -> Transport:
    """Сериализовать вложенную запись с каскадным удалением транспорта."""
    transport = await session.scalar(
        select(Transport).where(Transport.id == transport_id).with_for_update()
    )
    if transport is None:
        raise NotFound("Transport not found", resource=Transport.__name__, pk=str(transport_id))
    return transport


async def get_component(
    transport_id: UUID,
    component_id: UUID,
    *,
    session: AsyncSession,
    for_update: bool = False,
) -> TransportComponent:
    """Найти компонент только внутри parent path."""
    statement = select(TransportComponent).where(
        TransportComponent.id == component_id,
        TransportComponent.transport_id == transport_id,
    )
    if for_update:
        statement = statement.with_for_update()
    component = await session.scalar(statement)
    if component is None:
        raise NotFound(
            "TransportComponent not found",
            resource=TransportComponent.__name__,
            pk=str(component_id),
        )
    return component


async def get_rental(
    transport_id: UUID,
    rental_id: UUID,
    *,
    session: AsyncSession,
    for_update: bool = False,
) -> CourierTransport:
    """Найти аренду только внутри parent path и загрузить договор."""
    statement = (
        select(CourierTransport)
        .where(
            CourierTransport.id == rental_id,
            CourierTransport.transport_id == transport_id,
        )
        .options(joinedload(CourierTransport.file))
        .execution_options(populate_existing=True)
    )
    if for_update:
        statement = statement.with_for_update(of=CourierTransport)
    rental = await session.scalar(statement)
    if rental is None:
        raise NotFound(
            "CourierTransport not found",
            resource=CourierTransport.__name__,
            pk=str(rental_id),
        )
    return rental
