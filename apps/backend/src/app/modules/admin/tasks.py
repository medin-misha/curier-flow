"""Периодическая очистка истёкших refresh-сессий."""

from app.kernel.db import session as db_session
from app.modules.admin.services import admin_settings
from app.modules.admin.services import (
    purge_expired_refresh_tokens as purge_expired_refresh_tokens_service,
)
from app.platform.taskiq import schedule


@schedule(cron=admin_settings.refresh_cleanup_cron)
async def purge_expired_refresh_tokens() -> int:
    """Удалить refresh-токены после истечения их подписанного TTL."""
    return await purge_expired_refresh_tokens_service(
        session_factory=db_session.session_factory,
    )
