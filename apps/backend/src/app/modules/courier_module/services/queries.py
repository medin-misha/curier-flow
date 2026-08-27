"""Общие запросы courier aggregate и вложенных ресурсов."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.base import ExecutableOption

from app.kernel.errors import Conflict, NotFound
from app.modules.courier_module.models import (
    Courier,
    CourierDocument,
    CourierPlatformAccount,
)
from app.platform.files import File, FileStatus


def aggregate_options() -> tuple[ExecutableOption, ...]:
    """Явный eager contract aggregate без deleting File/Document."""
    documents = Courier.documents.and_(CourierDocument.file.has(File.status != FileStatus.DELETING))
    return (
        selectinload(Courier.platform_accounts),
        selectinload(documents).joinedload(CourierDocument.file),
    )


async def find_by_identity(
    email: str,
    phone: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> Courier | None:
    """Найти natural-key match или поднять identity-split."""
    async with session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(Courier)
                    .where(or_(Courier.email == email, Courier.phone == phone))
                    .options(*aggregate_options())
                    .order_by(Courier.id)
                )
            ).all()
        )
    if len(rows) > 1:
        raise Conflict(
            "Email and phone belong to different couriers",
            reason="identity-split",
        )
    return rows[0] if rows else None


async def load_courier_by_identity(
    email: str,
    phone: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> Courier:
    """Перечитать committed aggregate по natural keys."""
    courier = await find_by_identity(email, phone, session_factory=session_factory)
    if courier is None:
        raise RuntimeError("committed courier aggregate cannot be reloaded")
    return courier


async def get_document(
    courier_id: UUID,
    document_id: UUID,
    *,
    session: AsyncSession,
    for_update: bool = False,
) -> CourierDocument:
    """Найти видимый Document по собственному id и courier_id."""
    statement = (
        select(CourierDocument)
        .join(CourierDocument.file)
        .where(
            CourierDocument.id == document_id,
            CourierDocument.courier_id == courier_id,
            File.status != FileStatus.DELETING,
        )
        .options(joinedload(CourierDocument.file))
    )
    if for_update:
        statement = statement.with_for_update(of=CourierDocument)
    document = await session.scalar(statement)
    if document is None:
        raise NotFound(
            "CourierDocument not found",
            resource=CourierDocument.__name__,
            pk=str(document_id),
        )
    return document


async def get_platform_account(
    courier_id: UUID,
    account_id: UUID,
    *,
    session: AsyncSession,
) -> CourierPlatformAccount:
    """Найти account только внутри указанного Courier."""
    account = await session.scalar(
        select(CourierPlatformAccount).where(
            CourierPlatformAccount.id == account_id,
            CourierPlatformAccount.courier_id == courier_id,
        )
    )
    if account is None:
        raise NotFound(
            "CourierPlatformAccount not found",
            resource=CourierPlatformAccount.__name__,
            pk=str(account_id),
        )
    return account


async def require_courier(courier_id: UUID, *, session: AsyncSession) -> Courier:
    """Вернуть Courier или единообразный 404."""
    courier = await session.get(Courier, courier_id)
    if courier is None:
        raise NotFound("Courier not found", resource=Courier.__name__, pk=str(courier_id))
    return courier


async def lock_courier(courier_id: UUID, *, session: AsyncSession) -> None:
    """Сериализовать дочерний write с каскадным DELETE Courier."""
    found = await session.scalar(
        select(Courier.id).where(Courier.id == courier_id).with_for_update()
    )
    if found is None:
        raise NotFound("Courier not found", resource=Courier.__name__, pk=str(courier_id))
