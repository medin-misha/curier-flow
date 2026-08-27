"""Манифест admin-модуля и startup bootstrap первого администратора."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.kernel.db import session as db_session
from app.kernel.events.outbox import DOMAIN_EVENTS_EXCHANGE
from app.kernel.registry import Module, TopologyDecl
from app.modules.admin.events import CourierRegistrationTelegramNotificationCreated
from app.modules.admin.handlers import router
from app.modules.admin.services import (
    AdminSettings,
    admin_settings,
    bootstrap_first_admin,
)
from app.modules.admin.subscribers import handle_courier_registered
from app.modules.admin.tasks import purge_expired_refresh_tokens

TELEGRAM_NOTIFICATIONS_TOPOLOGY: Final = TopologyDecl(
    exchange=DOMAIN_EVENTS_EXCHANGE,
    queue="telegram.notifications",
    routing_key=CourierRegistrationTelegramNotificationCreated.topic,
    exchange_type="topic",
    durable=True,
    dead_letter=True,
    retry_ttl_ms=30_000,
)


def admin_lifespan(
    *,
    settings: AdminSettings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Создать lifespan, который bootstrap'ит первого Admin из `.env`."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await bootstrap_first_admin(
            session_factory=db_session.session_factory,
            settings=settings,
        )
        yield

    return lifespan


admin_module: Final = Module(
    name="admin",
    router=router,
    settings=AdminSettings,
    models="app.modules.admin.models",
    subscribers=(handle_courier_registered,),
    tasks=(purge_expired_refresh_tokens,),
    topology=(TELEGRAM_NOTIFICATIONS_TOPOLOGY,),
    lifespan=admin_lifespan(settings=admin_settings),
)
