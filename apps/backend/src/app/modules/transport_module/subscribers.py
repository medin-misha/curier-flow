"""Синхронизация контактов через идемпотентную проекцию событий."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.events.bus import subscribe
from app.modules.transport_module.events import CourierDeleted, CourierProfileChanged
from app.modules.transport_module.models.courier_profile import TransportCourierProfile


@subscribe(CourierProfileChanged, CourierDeleted)
async def sync_courier_profile(
    event: CourierProfileChanged | CourierDeleted, session: AsyncSession
) -> None:
    """Обновить контакт; tombstone исключает восстановление удалённых данных."""
    deleted = isinstance(event, CourierDeleted)
    statement = insert(TransportCourierProfile).values(
        courier_id=event.courier_id,
        full_name=event.full_name if isinstance(event, CourierProfileChanged) else None,
        phone=event.phone if isinstance(event, CourierProfileChanged) else None,
        source_updated_at=event.changed_at,
        is_deleted=deleted,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[TransportCourierProfile.courier_id],
            set_={
                "full_name": statement.excluded.full_name,
                "phone": statement.excluded.phone,
                "source_updated_at": statement.excluded.source_updated_at,
                "is_deleted": statement.excluded.is_deleted,
            },
            where=(
                ~TransportCourierProfile.is_deleted
                & (
                    statement.excluded.is_deleted
                    | (
                        statement.excluded.source_updated_at
                        > TransportCourierProfile.source_updated_at
                    )
                )
            ),
        )
    )
