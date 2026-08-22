"""Периодическая retention-задача courier_module."""

from app.kernel.db import session as db_session
from app.modules.courier_module.services import (
    courier_module_settings,
)
from app.modules.courier_module.services import (
    purge_expired_documents as purge_expired_documents_service,
)
from app.platform.taskiq import schedule


@schedule(cron=courier_module_settings.retention_cron)
async def purge_expired_documents() -> int:
    """Пометить Files и удалить Documents с истёкшим retention/hold."""
    return await purge_expired_documents_service(
        session_factory=db_session.session_factory,
        settings=courier_module_settings,
    )
