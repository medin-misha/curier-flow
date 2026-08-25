"""Управление администраторами и проверка текущей учётной записи."""

from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, NotFound, Unauthorized
from app.kernel.pagination import Page, PageParams
from app.kernel.security.passwords import hash_password
from app.kernel.security.tokens import TokenClaims
from app.modules.admin.models import Admin, AdminRefreshToken
from app.modules.admin.schemas.requests import AdminCreate, AdminPasswordReset, AdminPatch

#: Все операции, способные изменить число активных Admin, берут один
#: transaction-scoped PostgreSQL lock. Иначе две параллельные деактивации
#: увидят по два активных аккаунта и оставят систему без единого входа.
ADMIN_STATE_LOCK_KEY: Final = 0x43465241444D494E


async def authenticate_current_admin(
    claims: TokenClaims,
    *,
    session: AsyncSession,
) -> Admin:
    """Вернуть активного Admin, которому принадлежат access claims."""
    version = claims.payload.get("auth_version")
    if claims.payload.get("kind") != "admin" or type(version) is not int:
        raise _invalid_credentials()

    admin = await session.get(Admin, claims.subject)
    if admin is None or not admin.is_active or admin.auth_version != version:
        raise _invalid_credentials()
    return admin


async def create_admin(request: AdminCreate, *, session: AsyncSession) -> Admin:
    """Создать активного Admin, захешировав переданный пароль Argon2id."""
    admin = Admin(
        username=request.username,
        hashed_password=hash_password(request.password),
        telegram_id=request.telegram_id,
    )
    session.add(admin)
    try:
        await session.flush()
    except IntegrityError as error:
        raise Conflict(
            "An admin with this username or Telegram ID already exists",
            reason="duplicate-admin",
        ) from error
    return admin


async def get_admin(admin_id: UUID, *, session: AsyncSession) -> Admin:
    """Вернуть Admin по идентификатору или поднять NotFound."""
    return await CRUD.get_or_404(Admin, admin_id, session)


async def list_admins(page: PageParams, *, session: AsyncSession) -> Page[Admin]:
    """Вернуть keyset-страницу администраторов."""
    return await CRUD.list_page(Admin, session, page=page)


async def patch_admin(
    admin_id: UUID,
    patch: AdminPatch,
    *,
    session: AsyncSession,
) -> Admin:
    """Изменить username и/или Telegram ID администратора."""
    admin = await CRUD.get_or_404(Admin, admin_id, session)
    try:
        return await CRUD.update(admin, patch, session)
    except IntegrityError as error:
        raise Conflict(
            "An admin with this username or Telegram ID already exists",
            reason="duplicate-admin",
        ) from error


async def activate_admin(admin_id: UUID, *, session: AsyncSession) -> Admin:
    """Активировать Admin, сериализовав изменение множества активных аккаунтов."""
    await _lock_admin_state(session)
    admin = await _get_admin_for_update(admin_id, session)
    admin.is_active = True
    await session.flush()
    return admin


async def deactivate_admin(
    admin_id: UUID,
    *,
    actor: Admin,
    session: AsyncSession,
) -> Admin:
    """Деактивировать Admin, не разрешая self-lockout и удаление последнего."""
    if admin_id == actor.id:
        raise Conflict("An admin cannot deactivate itself", reason="self-deactivation")

    await _lock_admin_state(session)
    current_actor = await _get_admin_for_update(actor.id, session)
    if not current_actor.is_active:
        raise Unauthorized("Credentials are not valid", reason="invalid-credentials")
    admin = await _get_admin_for_update(admin_id, session)
    if not admin.is_active:
        return admin

    active = await session.scalar(select(func.count()).select_from(Admin).where(Admin.is_active))
    if active is None or active <= 1:
        raise Conflict(
            "The last active admin cannot be deactivated",
            reason="last-active-admin",
        )

    admin.is_active = False
    await _revoke_admin_tokens(admin.id, session=session)
    await session.flush()
    return admin


async def reset_admin_password(
    admin_id: UUID,
    request: AdminPasswordReset,
    *,
    session: AsyncSession,
) -> None:
    """Заменить пароль, увеличить auth_version и отозвать refresh-сессии."""
    admin = await _get_admin_for_update(admin_id, session)
    admin.hashed_password = hash_password(request.new_password)
    admin.auth_version += 1
    await _revoke_admin_tokens(admin.id, session=session)
    await session.flush()


async def _get_admin_for_update(admin_id: UUID, session: AsyncSession) -> Admin:
    """Заблокировать строку Admin для изменения или поднять NotFound."""
    admin = await session.scalar(
        select(Admin).where(Admin.id == admin_id).with_for_update(of=Admin)
    )
    if admin is None:
        raise NotFound("Admin not found", resource="Admin", pk=str(admin_id))
    return admin


async def _lock_admin_state(session: AsyncSession) -> None:
    """Взять transaction-scoped lock для bootstrap/activation/deactivation."""
    await session.execute(select(func.pg_advisory_xact_lock(ADMIN_STATE_LOCK_KEY)))


async def _revoke_admin_tokens(admin_id: UUID, *, session: AsyncSession) -> None:
    """Отозвать все ещё действующие refresh-токены Admin."""
    await session.execute(
        update(AdminRefreshToken)
        .where(
            AdminRefreshToken.admin_id == admin_id,
            AdminRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(tz=UTC))
    )


def _invalid_credentials() -> Unauthorized:
    """Собрать одинаковую ошибку для всех негодных admin credentials."""
    return Unauthorized("Credentials are not valid", reason="invalid-credentials")
