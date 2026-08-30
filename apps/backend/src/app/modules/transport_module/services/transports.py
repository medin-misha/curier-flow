"""Создание, список, изменение и удаление транспорта."""

from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import exists, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.pagination import Page, PageParams, decode_cursor, encode_cursor
from app.modules.transport_module.models import CourierTransport, Transport
from app.modules.transport_module.schemas.requests import TransportCreate, TransportPatch
from app.modules.transport_module.services.common import (
    normalize_serial_number,
    normalize_transport_type,
    normalize_trimmed,
    raise_known_integrity,
    validate_deposit,
)
from app.modules.transport_module.services.queries import (
    active_rental_option,
    get_transport,
    lock_transport,
)


async def create_transport(request: TransportCreate, *, session: AsyncSession) -> Transport:
    """Нормализовать и создать транспорт."""
    normalized = request.model_copy(
        update={
            "type": normalize_transport_type(request.type),
            "model": normalize_trimmed(request.model, field="model", maximum=128),
            "serial_number": normalize_serial_number(request.serial_number),
            "color": normalize_trimmed(request.color, field="color", maximum=64),
        }
    )
    validate_deposit(normalized.deposit_required, normalized.deposit_amount)
    try:
        transport = await CRUD.create(Transport, normalized, session)
    except IntegrityError as error:
        raise_known_integrity(error)
    return await get_transport(transport.id, session=session)


async def list_transports(
    page: PageParams,
    *,
    session: AsyncSession,
    transport_type: str | None = None,
    serial_number: str | None = None,
    courier_id: UUID | None = None,
    is_available: bool | None = None,
) -> Page[Transport]:
    """Вернуть keyset-страницу с фильтрами текущей аренды."""
    active = exists(
        select(CourierTransport.id).where(
            CourierTransport.transport_id == Transport.id,
            CourierTransport.ended_at.is_(None),
        )
    )
    where = []
    if transport_type is not None:
        where.append(Transport.type == normalize_transport_type(transport_type))
    if serial_number is not None:
        where.append(Transport.serial_number == normalize_serial_number(serial_number))
    if courier_id is not None:
        where.append(
            exists(
                select(CourierTransport.id).where(
                    CourierTransport.transport_id == Transport.id,
                    CourierTransport.courier_id == courier_id,
                    CourierTransport.ended_at.is_(None),
                )
            )
        )
    if is_available is not None:
        where.append(~active if is_available else active)

    statement = (
        select(Transport)
        .where(*where)
        .options(active_rental_option())
        .execution_options(populate_existing=True)
        .order_by(Transport.created_at.desc(), Transport.id.desc())
        .limit(page.limit + 1)
    )
    if page.cursor is not None:
        position = decode_cursor(page.cursor)
        statement = statement.where(
            tuple_(Transport.created_at, Transport.id) < (position.created_at, position.id)
        )
    rows = list((await session.scalars(statement)).all())
    items = rows[: page.limit]
    next_cursor = None
    if len(rows) > page.limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return Page(items=items, next_cursor=next_cursor)


async def patch_transport(
    transport_id: UUID,
    patch: TransportPatch,
    *,
    session: AsyncSession,
) -> Transport:
    """Проверить итоговое состояние залога и применить PATCH."""
    transport = await lock_transport(transport_id, session=session)
    updates: dict[str, object] = {}
    if "type" in patch.model_fields_set:
        updates["type"] = normalize_transport_type(cast(str, patch.type))
    if "model" in patch.model_fields_set:
        updates["model"] = normalize_trimmed(cast(str, patch.model), field="model", maximum=128)
    if "serial_number" in patch.model_fields_set:
        updates["serial_number"] = normalize_serial_number(cast(str, patch.serial_number))
    if "color" in patch.model_fields_set:
        updates["color"] = normalize_trimmed(cast(str, patch.color), field="color", maximum=64)

    required = (
        cast(bool, patch.deposit_required)
        if "deposit_required" in patch.model_fields_set
        else transport.deposit_required
    )
    amount = (
        cast(Decimal, patch.deposit_amount)
        if "deposit_amount" in patch.model_fields_set
        else transport.deposit_amount
    )
    if "deposit_required" in patch.model_fields_set and not required:
        amount = None
        updates["deposit_amount"] = None
    validate_deposit(required, amount)

    normalized = patch.model_copy(update=updates)
    try:
        await CRUD.update(transport, normalized, session)
    except IntegrityError as error:
        raise_known_integrity(error)
    return await get_transport(transport_id, session=session)


async def delete_transport(transport_id: UUID, *, session: AsyncSession) -> None:
    """Каскадно удалить транспорт, если история не защищена договором."""
    transport = await lock_transport(transport_id, session=session)
    try:
        await CRUD.delete(transport, session)
    except IntegrityError as error:
        raise_known_integrity(error)
