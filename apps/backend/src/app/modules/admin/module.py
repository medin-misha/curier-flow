"""Манифест admin-модуля и startup bootstrap первого администратора."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.kernel.db import session as db_session
from app.kernel.registry import Module
from app.modules.admin.handlers import router
from app.modules.admin.services import AdminSettings, admin_settings, bootstrap_first_admin
from app.modules.admin.tasks import purge_expired_refresh_tokens


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
    tasks=(purge_expired_refresh_tokens,),
    lifespan=admin_lifespan(settings=admin_settings),
)
