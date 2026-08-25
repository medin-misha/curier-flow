"""HTTP-ручки администраторов, Bearer access и refresh cookie."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.context import actor_id
from app.kernel.db import session as db_session
from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.errors import Unauthorized
from app.kernel.idempotency import idempotent
from app.kernel.pagination import Page, PageParams
from app.kernel.security.tokens import TokenType, decode_token, jwt_settings
from app.modules.admin.models import Admin
from app.modules.admin.schemas.requests import (
    AdminCreate,
    AdminLogin,
    AdminPasswordReset,
    AdminPatch,
)
from app.modules.admin.schemas.responses import AccessTokenResponse, AdminResponse
from app.modules.admin.services import (
    TokenGrant,
    activate_admin,
    admin_settings,
    authenticate_current_admin,
    create_admin,
    deactivate_admin,
    get_admin,
    list_admins,
    login_admin,
    logout_admin,
    patch_admin,
    refresh_admin_tokens,
    reset_admin_password,
)

Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
PageQuery = Annotated[PageParams, Depends()]

_bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)]
RefreshCookie = Annotated[
    str | None,
    Cookie(alias=admin_settings.refresh_cookie_name),
]


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Отдать актуальную фабрику для refresh rotation с собственной границей."""
    return db_session.session_factory


Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


async def get_current_admin(
    credentials: BearerCredentials,
    session: RoSession,
) -> Admin:
    """Проверить access JWT и вернуть актуального активного Admin."""
    if credentials is None:
        raise Unauthorized(
            "Authentication is required for this operation",
            reason="missing-token",
        )
    claims = decode_token(
        credentials.credentials,
        expected=TokenType.ACCESS,
        settings=jwt_settings,
    )
    admin = await authenticate_current_admin(claims, session=session)
    actor_id.set(admin.id)
    return admin


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]

router = APIRouter(tags=["admin"])
auth_router = APIRouter(prefix="/auth")
admins_router = APIRouter(prefix="/admins")


@auth_router.post("/login", summary="Authenticate an admin")
async def login(body: AdminLogin, response: Response, uow: Uow) -> AccessTokenResponse:
    """Проверить пароль, создать refresh family и вернуть access JWT."""
    grant = await login_admin(body, session=uow)
    _set_refresh_cookie(response, grant)
    return _access_response(grant)


@auth_router.post("/refresh", summary="Rotate an admin refresh token")
async def refresh(
    response: Response,
    sessions: Sessions,
    refresh_token: RefreshCookie = None,
) -> AccessTokenResponse:
    """Одноразово обменять refresh cookie на новую пару."""
    if refresh_token is None:
        raise Unauthorized("Refresh token is required", reason="missing-refresh-token")
    grant = await refresh_admin_tokens(refresh_token, session_factory=sessions)
    _set_refresh_cookie(response, grant)
    return _access_response(grant)


@auth_router.post(
    "/logout",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Revoke the admin refresh family",
)
async def logout(
    response: Response,
    sessions: Sessions,
    refresh_token: RefreshCookie = None,
) -> None:
    """Отозвать refresh family и удалить cookie; повтор безопасен."""
    await logout_admin(refresh_token, session_factory=sessions)
    response.delete_cookie(
        admin_settings.refresh_cookie_name,
        path="/admin/auth",
        secure=admin_settings.refresh_cookie_secure,
        httponly=True,
        samesite=admin_settings.refresh_cookie_samesite,
    )


@admins_router.get("/me", summary="Current admin")
async def me(current: CurrentAdmin) -> AdminResponse:
    """Вернуть действующего администратора."""
    return AdminResponse.model_validate(current)


@admins_router.post("", status_code=HTTPStatus.CREATED, summary="Create an admin")
@idempotent
async def create(
    body: AdminCreate,
    uow: Uow,
    _current: CurrentAdmin,
) -> AdminResponse:
    """Создать администратора; повтор требует Idempotency-Key."""
    return AdminResponse.model_validate(await create_admin(body, session=uow))


@admins_router.get("", summary="List admins")
async def list_page(
    page: PageQuery,
    session: RoSession,
    _current: CurrentAdmin,
) -> Page[AdminResponse]:
    """Отдать keyset-страницу администраторов."""
    found = await list_admins(page, session=session)
    return Page[AdminResponse](
        items=[AdminResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@admins_router.get("/{admin_id}", summary="Admin by id")
async def retrieve(
    admin_id: UUID,
    session: RoSession,
    _current: CurrentAdmin,
) -> AdminResponse:
    """Вернуть выбранного администратора."""
    return AdminResponse.model_validate(await get_admin(admin_id, session=session))


@admins_router.patch("/{admin_id}", summary="Update admin fields")
async def update(
    admin_id: UUID,
    body: AdminPatch,
    uow: Uow,
    _current: CurrentAdmin,
) -> AdminResponse:
    """Изменить username и/или Telegram ID."""
    return AdminResponse.model_validate(await patch_admin(admin_id, body, session=uow))


@admins_router.post("/{admin_id}/activate", summary="Activate an admin")
async def activate(
    admin_id: UUID,
    uow: Uow,
    _current: CurrentAdmin,
) -> AdminResponse:
    """Активировать выбранного администратора."""
    return AdminResponse.model_validate(await activate_admin(admin_id, session=uow))


@admins_router.post("/{admin_id}/deactivate", summary="Deactivate an admin")
async def deactivate(
    admin_id: UUID,
    uow: Uow,
    current: CurrentAdmin,
) -> AdminResponse:
    """Деактивировать не текущего и не последнего активного Admin."""
    return AdminResponse.model_validate(
        await deactivate_admin(admin_id, actor=current, session=uow)
    )


@admins_router.post(
    "/{admin_id}/reset-password",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Reset an admin password",
)
async def reset_password(
    admin_id: UUID,
    body: AdminPasswordReset,
    uow: Uow,
    _current: CurrentAdmin,
) -> None:
    """Заменить пароль и отозвать все refresh-сессии выбранного Admin."""
    await reset_admin_password(admin_id, body, session=uow)


def _set_refresh_cookie(response: Response, grant: TokenGrant) -> None:
    """Установить refresh JWT только в ограниченную HttpOnly cookie."""
    # POST обычно не кешируется, но token responses содержат credentials и не
    # должны зависеть от эвристик браузера, reverse proxy или CDN.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.set_cookie(
        admin_settings.refresh_cookie_name,
        grant.refresh_token,
        max_age=jwt_settings.refresh_ttl,
        path="/admin/auth",
        secure=admin_settings.refresh_cookie_secure,
        httponly=True,
        samesite=admin_settings.refresh_cookie_samesite,
    )


def _access_response(grant: TokenGrant) -> AccessTokenResponse:
    """Собрать публичную часть выданной пары токенов."""
    return AccessTokenResponse(
        access_token=grant.access_token,
        expires_in=grant.expires_in,
    )


router.include_router(auth_router)
router.include_router(admins_router)
