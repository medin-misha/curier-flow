"""Подготовка интеграционных событий Telegram-уведомлений."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.events.bus import emit
from app.modules.admin.events import (
    CourierRegistered,
    CourierRegistrationTelegramNotificationCreated,
)
from app.modules.admin.models import Admin


async def fan_out_courier_registration_notifications(
    event: CourierRegistered,
    *,
    session: AsyncSession,
) -> None:
    """Создать notification event для каждой пары active linked Admin × platform."""
    telegram_ids = (
        await session.scalars(
            select(Admin.telegram_id).where(
                Admin.is_active.is_(True),
                Admin.telegram_id.is_not(None),
            )
        )
    ).all()

    for telegram_id in telegram_ids:
        if telegram_id is None:  # pragma: no cover - SQL predicate narrows rows at the DB boundary
            continue
        for platform in event.platforms:
            emit(
                session,
                CourierRegistrationTelegramNotificationCreated(
                    telegram_id=telegram_id,
                    full_name=event.full_name,
                    contact_platform=event.contact_platform,
                    contact=event.contact,
                    platform=platform,
                ),
            )
