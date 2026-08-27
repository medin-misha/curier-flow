"""Подписчики административного модуля на чужие доменные факты."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.events.bus import subscribe
from app.modules.admin.events import CourierRegistered
from app.modules.admin.services import fan_out_courier_registration_notifications


@subscribe(CourierRegistered)
async def handle_courier_registered(
    event: CourierRegistered,
    session: AsyncSession,
) -> None:
    """Передать courier.registered в транзакционный fan-out сервис."""
    await fan_out_courier_registration_notifications(event, session=session)
