"""Startup bootstrap первого администратора из настроек окружения."""

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.security.passwords import hash_password
from app.modules.admin.models import Admin
from app.modules.admin.schemas.requests import normalize_username, validate_password
from app.modules.admin.services.accounts import ADMIN_STATE_LOCK_KEY
from app.modules.admin.services.settings import AdminSettings

_logger = structlog.get_logger("app.modules.admin")


async def bootstrap_first_admin(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: AdminSettings,
) -> Admin | None:
    """Создать первого Admin при пустой таблице, иначе выполнить no-op."""
    async with session_factory() as session, session.begin():
        await session.execute(select(func.pg_advisory_xact_lock(ADMIN_STATE_LOCK_KEY)))
        exists = await session.scalar(select(Admin.id).limit(1))
        if exists is not None:
            return None

        try:
            username = normalize_username(settings.bootstrap_username)
        except ValueError as error:
            raise RuntimeError("ADMIN_BOOTSTRAP_USERNAME is missing or invalid") from error

        password = settings.bootstrap_password.get_secret_value()
        try:
            validate_password(password)
        except ValueError as error:
            raise RuntimeError(
                "ADMIN_BOOTSTRAP_PASSWORD must contain between 12 and 128 characters"
            ) from error
        if settings.bootstrap_telegram_id is not None and settings.bootstrap_telegram_id <= 0:
            raise RuntimeError("ADMIN_BOOTSTRAP_TELEGRAM_ID must be positive")

        admin = Admin(
            username=username,
            hashed_password=hash_password(password),
            telegram_id=settings.bootstrap_telegram_id,
        )
        session.add(admin)
        await session.flush()

    _logger.info("admin.bootstrap_created", admin_id=str(admin.id), username=admin.username)
    return admin
