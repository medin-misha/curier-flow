"""Login, refresh rotation, logout и retention refresh-токенов."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.errors import Unauthorized
from app.kernel.security.passwords import hash_password, password_needs_rehash, verify_password
from app.kernel.security.tokens import (
    TokenPair,
    TokenType,
    decode_token,
    issue_tokens,
    jwt_settings,
)
from app.modules.admin.models import Admin, AdminRefreshToken
from app.modules.admin.schemas.requests import AdminLogin

#: Настоящий Argon2id hash фиктивного пароля. Проверяется для неизвестного
#: username, чтобы время ответа не выдавало существование учётной записи.
DUMMY_HASH: Final = (
    "$argon2id$v=19$m=65536,t=3,p=4$MvFB1wt0KD/9NpidGTTGcw$"
    "YuVZgIx+YOc3JPLLz095wWY+W/XaUrY8MNCNWyEyrmo"
)


@dataclass(frozen=True, slots=True)
class TokenGrant:
    """Access для ответа и refresh для установки в HttpOnly cookie."""

    access_token: str
    refresh_token: str
    expires_in: int


async def login_admin(request: AdminLogin, *, session: AsyncSession) -> TokenGrant:
    """Проверить credentials, при необходимости rehash и создать token family."""
    admin = await session.scalar(select(Admin).where(Admin.username == request.username))
    candidate_hash = DUMMY_HASH if admin is None else admin.hashed_password
    password_is_valid = verify_password(request.password, candidate_hash)
    if not password_is_valid or admin is None or not admin.is_active:
        raise _invalid_credentials()

    if password_needs_rehash(admin.hashed_password):
        admin.hashed_password = hash_password(request.password)
        await session.flush()

    return await _issue_grant(admin, family_id=uuid4(), session=session)


async def refresh_admin_tokens(
    refresh_token: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> TokenGrant:
    """Одноразово ротировать refresh JWT или зафиксировать reuse-отзыв family."""
    claims = decode_token(refresh_token, expected=TokenType.REFRESH, settings=jwt_settings)
    token_hash = _token_hash(refresh_token)
    grant: TokenGrant | None = None
    rejection: Unauthorized | None = None

    async with session_factory() as session, session.begin():
        stored = await session.scalar(
            select(AdminRefreshToken)
            .where(AdminRefreshToken.id == claims.token_id)
            .with_for_update(of=AdminRefreshToken)
        )
        if stored is None:
            rejection = _invalid_credentials()
        elif (
            not hmac.compare_digest(stored.token_hash, token_hash)
            or stored.used_at is not None
            or stored.revoked_at is not None
        ):
            await _revoke_family(stored.family_id, session=session)
            rejection = _invalid_credentials(reason="refresh-reuse")
        else:
            admin = await session.get(Admin, stored.admin_id)
            if (
                admin is None
                or not admin.is_active
                or admin.auth_version != stored.auth_version
                or claims.subject != stored.admin_id
            ):
                await _revoke_family(stored.family_id, session=session)
                rejection = _invalid_credentials()
            else:
                stored.used_at = datetime.now(tz=UTC)
                grant = await _issue_grant(admin, family_id=stored.family_id, session=session)

    # Reuse обязан сначала закоммитить отзыв семейства. Исключение внутри
    # session.begin() откатило бы именно тот защитный эффект, ради которого
    # reuse был обнаружен.
    if rejection is not None:
        raise rejection
    if grant is None:  # pragma: no cover - все ветки выше заполняют одно из двух
        raise RuntimeError("Refresh rotation finished without a result")
    return grant


async def logout_admin(
    refresh_token: str | None,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Отозвать token family; отсутствие/мусор остаются безопасным no-op."""
    if refresh_token is None:
        return
    try:
        claims = decode_token(refresh_token, expected=TokenType.REFRESH, settings=jwt_settings)
    except Unauthorized:
        return

    async with session_factory() as session, session.begin():
        stored = await session.get(AdminRefreshToken, claims.token_id)
        if stored is not None:
            await _revoke_family(stored.family_id, session=session)


async def purge_expired_refresh_tokens(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime | None = None,
) -> int:
    """Удалить refresh-сессии, токены которых уже невозможно предъявить."""
    current = now or datetime.now(tz=UTC)
    async with session_factory() as session, session.begin():
        result = cast(
            CursorResult[tuple[()]],
            await session.execute(
                delete(AdminRefreshToken).where(AdminRefreshToken.expires_at < current)
            ),
        )
    return result.rowcount


async def _issue_grant(
    admin: Admin,
    *,
    family_id: UUID,
    session: AsyncSession,
) -> TokenGrant:
    """Выпустить пару и сохранить только hash её refresh JWT."""
    pair = issue_tokens(
        admin.id,
        settings=jwt_settings,
        claims={"kind": "admin", "auth_version": admin.auth_version},
    )
    refresh_claims = decode_token(
        pair.refresh_token,
        expected=TokenType.REFRESH,
        settings=jwt_settings,
    )
    session.add(
        AdminRefreshToken(
            id=refresh_claims.token_id,
            admin_id=admin.id,
            family_id=family_id,
            token_hash=_token_hash(pair.refresh_token),
            auth_version=admin.auth_version,
            expires_at=refresh_claims.expires_at,
        )
    )
    await session.flush()
    return _grant(pair)


async def _revoke_family(family_id: UUID, *, session: AsyncSession) -> None:
    """Отозвать все ещё действующие refresh-токены семейства."""
    await session.execute(
        update(AdminRefreshToken)
        .where(
            AdminRefreshToken.family_id == family_id,
            AdminRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(tz=UTC))
    )


def _token_hash(token: str) -> str:
    """Вернуть SHA-256 refresh JWT для хранения и постоянного сравнения."""
    return hashlib.sha256(token.encode()).hexdigest()


def _grant(pair: TokenPair) -> TokenGrant:
    """Преобразовать kernel TokenPair во внутренний результат модуля."""
    return TokenGrant(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


def _invalid_credentials(*, reason: str = "invalid-credentials") -> Unauthorized:
    """Собрать неразличимую наружу ошибку credentials."""
    return Unauthorized("Credentials are not valid", reason=reason)
