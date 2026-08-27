"""Retention orchestration документов courier_module."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.courier_module.models import (
    CourierDocument,
    DocumentPurpose,
    DocumentType,
)
from app.modules.courier_module.services.settings import CourierModuleSettings
from app.platform.files import mark_file_deleting

_logger = structlog.get_logger("app.modules.courier_module")


async def purge_expired_documents(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: CourierModuleSettings,
    now: datetime | None = None,
) -> int:
    """Одним SKIP LOCKED batch удалить eligible Documents и пометить Files.

    Ошибка одного элемента откатывает только savepoint этого элемента. S3 не
    вызывается: физический lifecycle остаётся универсальной задачей storage.
    """
    current = now or datetime.now(tz=UTC)
    retention_days = {
        DocumentPurpose.PLATFORM_ONBOARDING: settings.retention_platform_onboarding_days,
        DocumentPurpose.EMPLOYMENT_COMPLIANCE: (settings.retention_employment_compliance_days),
        DocumentPurpose.OTHER: settings.retention_other_days,
    }
    eligible = and_(
        or_(
            *(
                and_(
                    CourierDocument.type == document_type,
                    CourierDocument.purpose == purpose,
                    CourierDocument.created_at <= current - timedelta(days=days),
                )
                for document_type in DocumentType
                for purpose, days in retention_days.items()
            )
        ),
        or_(
            CourierDocument.legal_hold_until.is_(None),
            CourierDocument.legal_hold_until <= current,
        ),
    )
    purged = 0
    async with session_factory() as session, session.begin():
        documents = list(
            (
                await session.scalars(
                    select(CourierDocument)
                    .where(eligible)
                    .order_by(CourierDocument.created_at, CourierDocument.id)
                    .limit(settings.retention_batch_size)
                    .with_for_update(skip_locked=True, of=CourierDocument)
                )
            ).all()
        )
        for document in documents:
            try:
                async with session.begin_nested():
                    await mark_file_deleting(session, document.file_id)
                    await session.delete(document)
                    await session.flush()
            except Exception as error:
                _logger.warning(
                    "courier.retention_document_failed",
                    document_id=str(document.id),
                    error=type(error).__name__,
                )
                continue
            purged += 1
    return purged
