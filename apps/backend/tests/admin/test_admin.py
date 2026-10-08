"""Admin: управление аккаунтами, JWT, refresh rotation и startup bootstrap."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Final, cast
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from httpx import AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import Table, delete, select

from app.kernel.db import session as session_module
from app.kernel.security.passwords import hash_password, verify_password
from app.kernel.security.tokens import TokenType, decode_token, issue_tokens, jwt_settings
from app.modules.admin.models import Admin, AdminRefreshToken
from app.modules.admin.module import admin_lifespan, admin_module
from app.modules.admin.services import (
    AdminSettings,
    bootstrap_first_admin,
    purge_expired_refresh_tokens,
)
from app.modules.admin.services import authentication as auth_service
from tests.asgi import app_client

PASSWORD: Final = "correct horse battery staple"  # noqa: S105
NEW_PASSWORD: Final = "another correct horse battery"  # noqa: S105
COOKIE: Final = "admin_refresh"
IDEMPOTENCY_KEY: Final = "admin-test-key"


@pytest.fixture
async def admin_database(clean_db: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Очистить собственные таблицы нового модуля в порядке внешних ключей."""
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(AdminRefreshToken))
        await session.execute(delete(Admin))
    yield


@pytest.fixture
async def http(admin_database: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    async with app_client([admin_module]) as client:
        yield client


async def seed_admin(
    *,
    username: str = "root",
    password: str = PASSWORD,
    telegram_id: int | None = 1001,
    is_active: bool = True,
    auth_version: int = 1,
    hashed_password: str | None = None,
) -> Admin:
    """Создать Admin напрямую: HTTP create сам требует действующего Admin."""
    async with session_module.session_factory() as session, session.begin():
        admin = Admin(
            username=username,
            hashed_password=hashed_password or hash_password(password),
            telegram_id=telegram_id,
            is_active=is_active,
            auth_version=auth_version,
        )
        session.add(admin)
        await session.flush()
    return admin


def access_for(admin: Admin, *, version: int | None = None) -> str:
    """Выпустить access JWT с admin claims для подготовленной строки."""
    return issue_tokens(
        admin.id,
        settings=jwt_settings,
        claims={
            "kind": "admin",
            "auth_version": admin.auth_version if version is None else version,
        },
    ).access_token


def authorization(admin: Admin, *, version: int | None = None) -> dict[str, str]:
    """Собрать Bearer-заголовок для защищённых admin endpoints."""
    return {"authorization": f"Bearer {access_for(admin, version=version)}"}


async def login(
    client: AsyncClient, *, username: str = "root", password: str = PASSWORD
) -> Response:
    """Выполнить login с валидным по схеме телом."""
    return await client.post(
        "/admin/auth/login",
        json={"username": username, "password": password},
    )


async def test_login_returns_only_access_and_sets_an_http_only_cookie(http: AsyncClient) -> None:
    admin = await seed_admin()

    response = await login(http)

    assert response.status_code == HTTPStatus.OK
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert response.json()["token_type"] == "bearer"  # noqa: S105
    assert "refresh_token" not in response.text
    cookie = response.headers["set-cookie"]
    assert f"{COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"

    claims = decode_token(
        response.json()["access_token"],
        expected=TokenType.ACCESS,
        settings=jwt_settings,
    )
    assert claims.subject == admin.id
    assert claims.payload["kind"] == "admin"
    assert claims.payload["auth_version"] == admin.auth_version


async def test_plaintext_password_and_refresh_are_not_stored(http: AsyncClient) -> None:
    await seed_admin()

    response = await login(http)
    refresh = response.cookies[COOKIE]

    async with session_module.session_factory() as session:
        admin = await session.scalar(select(Admin).where(Admin.username == "root"))
        stored = await session.scalar(select(AdminRefreshToken))

    assert admin is not None
    assert PASSWORD not in admin.hashed_password
    assert verify_password(PASSWORD, admin.hashed_password)
    assert stored is not None
    assert stored.token_hash != refresh
    assert len(stored.token_hash) == 64


async def test_unknown_username_and_wrong_password_have_the_same_response(
    http: AsyncClient,
) -> None:
    await seed_admin()

    unknown = await login(http, username="unknown")
    wrong = await login(http, password="wrong password long enough")  # noqa: S106

    assert unknown.status_code == wrong.status_code == HTTPStatus.UNAUTHORIZED
    assert unknown.json()["detail"] == wrong.json()["detail"] == "Credentials are not valid"
    assert unknown.json()["reason"] == wrong.json()["reason"] == "invalid-credentials"


async def test_unknown_username_still_verifies_the_dummy_hash(
    http: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    original = verify_password

    def recording_verify(password: str, hashed: str) -> bool:
        seen.append(hashed)
        return original(password, hashed)

    monkeypatch.setattr(auth_service, "verify_password", recording_verify)

    await login(http, username="unknown")

    assert seen == [auth_service.DUMMY_HASH]


async def test_successful_login_rehashes_an_old_password(http: AsyncClient) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    old_hash = hash_password(PASSWORD, hasher=weak)
    admin = await seed_admin(hashed_password=old_hash)

    response = await login(http)

    assert response.status_code == HTTPStatus.OK
    async with session_module.session_factory() as session:
        reloaded = await session.get(Admin, admin.id)
    assert reloaded is not None
    assert reloaded.hashed_password != old_hash
    assert verify_password(PASSWORD, reloaded.hashed_password)


async def test_current_admin_requires_a_live_matching_account(http: AsyncClient) -> None:
    admin = await seed_admin()
    missing_admin = issue_tokens(
        uuid4(),
        settings=jwt_settings,
        claims={"kind": "admin", "auth_version": 1},
    ).access_token

    missing = await http.get("/admin/admins/me")
    deleted = await http.get(
        "/admin/admins/me",
        headers={"authorization": f"Bearer {missing_admin}"},
    )
    valid = await http.get("/admin/admins/me", headers=authorization(admin))
    wrong_version = await http.get(
        "/admin/admins/me",
        headers=authorization(admin, version=admin.auth_version + 1),
    )

    assert missing.status_code == HTTPStatus.UNAUTHORIZED
    assert deleted.status_code == HTTPStatus.UNAUTHORIZED
    assert valid.status_code == HTTPStatus.OK
    assert valid.json()["id"] == str(admin.id)
    assert "hashed_password" not in valid.text
    assert wrong_version.status_code == HTTPStatus.UNAUTHORIZED


async def test_disabled_admin_cannot_authenticate(http: AsyncClient) -> None:
    admin = await seed_admin(is_active=False)

    login_response = await login(http)
    current = await http.get("/admin/admins/me", headers=authorization(admin))

    assert login_response.status_code == HTTPStatus.UNAUTHORIZED
    assert current.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_is_idempotent_and_duplicate_fields_are_conflicts(http: AsyncClient) -> None:
    root = await seed_admin()
    headers = {**authorization(root), "Idempotency-Key": IDEMPOTENCY_KEY}
    body = {"username": "second", "password": PASSWORD, "telegram_id": 2002}

    created = await http.post("/admin/admins", headers=headers, json=body)
    replayed = await http.post("/admin/admins", headers=headers, json=body)
    duplicate = await http.post(
        "/admin/admins",
        headers={**authorization(root), "Idempotency-Key": "another-key"},
        json={**body, "telegram_id": 3003},
    )
    duplicate_telegram = await http.post(
        "/admin/admins",
        headers={**authorization(root), "Idempotency-Key": "third-key"},
        json={**body, "username": "third"},
    )

    assert created.status_code == HTTPStatus.CREATED
    assert replayed.status_code == HTTPStatus.CREATED
    assert replayed.headers["Idempotency-Replayed"] == "true"
    assert replayed.content == created.content
    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.json()["reason"] == "duplicate-admin"
    assert duplicate_telegram.status_code == HTTPStatus.CONFLICT
    assert duplicate_telegram.json()["reason"] == "duplicate-admin"


async def test_admin_list_uses_keyset_pagination(http: AsyncClient) -> None:
    root = await seed_admin()
    await seed_admin(username="second", telegram_id=2002)
    await seed_admin(username="third", telegram_id=3003)

    first = (
        await http.get(
            "/admin/admins",
            params={"limit": 2},
            headers=authorization(root),
        )
    ).json()
    rest = (
        await http.get(
            "/admin/admins",
            params={"cursor": first["next_cursor"]},
            headers=authorization(root),
        )
    ).json()

    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None


async def test_patch_allows_clearing_telegram_but_not_username(http: AsyncClient) -> None:
    admin = await seed_admin()

    cleared = await http.patch(
        f"/admin/admins/{admin.id}",
        headers=authorization(admin),
        json={"telegram_id": None},
    )
    invalid = await http.patch(
        f"/admin/admins/{admin.id}",
        headers=authorization(admin),
        json={"username": None},
    )

    assert cleared.status_code == HTTPStatus.OK
    assert cleared.json()["telegram_id"] is None
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_refresh_rotates_and_reuse_revokes_the_new_token(http: AsyncClient) -> None:
    await seed_admin()
    logged_in = await login(http)
    old_refresh = logged_in.cookies[COOKIE]

    rotated = await http.post("/admin/auth/refresh")
    new_refresh = rotated.cookies[COOKIE]
    http.cookies.clear()
    http.cookies.set(COOKIE, old_refresh)
    reuse = await http.post("/admin/auth/refresh")
    http.cookies.clear()
    http.cookies.set(COOKIE, new_refresh)
    after_reuse = await http.post("/admin/auth/refresh")

    assert rotated.status_code == HTTPStatus.OK
    assert new_refresh != old_refresh
    assert reuse.status_code == HTTPStatus.UNAUTHORIZED
    assert reuse.json()["reason"] == "refresh-reuse"
    assert after_reuse.status_code == HTTPStatus.UNAUTHORIZED


async def test_parallel_refresh_leaves_no_two_active_branches(
    admin_database: None,  # noqa: ARG001
) -> None:
    await seed_admin()
    async with app_client([admin_module]) as login_client:
        old_refresh = (await login(login_client)).cookies[COOKIE]

    async with (
        app_client([admin_module]) as first,
        app_client([admin_module]) as second,
    ):
        first.cookies.set(COOKIE, old_refresh)
        second.cookies.set(COOKIE, old_refresh)
        responses = await asyncio.gather(
            first.post("/admin/auth/refresh"),
            second.post("/admin/auth/refresh"),
        )

    assert sorted(response.status_code for response in responses) == [
        HTTPStatus.OK,
        HTTPStatus.UNAUTHORIZED,
    ]
    async with session_module.session_factory() as session:
        tokens = list((await session.scalars(select(AdminRefreshToken))).all())
    assert len(tokens) == 2
    assert all(token.used_at is not None or token.revoked_at is not None for token in tokens)


async def test_logout_is_a_repeatable_no_op_and_clears_cookie(http: AsyncClient) -> None:
    await seed_admin()
    await login(http)

    first = await http.post("/admin/auth/logout")
    second = await http.post("/admin/auth/logout")

    assert first.status_code == second.status_code == HTTPStatus.NO_CONTENT
    assert f'{COOKIE}=""' in first.headers["set-cookie"]


async def test_password_reset_invalidates_old_credentials(http: AsyncClient) -> None:
    root = await seed_admin()
    target = await seed_admin(username="target", telegram_id=2002)
    target_login = await login(http, username="target")
    old_access = target_login.json()["access_token"]

    reset = await http.post(
        f"/admin/admins/{target.id}/reset-password",
        headers=authorization(root),
        json={"new_password": NEW_PASSWORD},
    )
    old_current = await http.get(
        "/admin/admins/me",
        headers={"authorization": f"Bearer {old_access}"},
    )
    old_rotation = await http.post("/admin/auth/refresh")

    assert reset.status_code == HTTPStatus.NO_CONTENT
    assert old_current.status_code == HTTPStatus.UNAUTHORIZED
    assert old_rotation.status_code == HTTPStatus.UNAUTHORIZED
    assert (await login(http, username="target")).status_code == HTTPStatus.UNAUTHORIZED
    assert (
        await login(http, username="target", password=NEW_PASSWORD)
    ).status_code == HTTPStatus.OK


async def test_admin_cannot_deactivate_itself(http: AsyncClient) -> None:
    admin = await seed_admin()

    response = await http.post(
        f"/admin/admins/{admin.id}/deactivate",
        headers=authorization(admin),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["reason"] == "self-deactivation"


async def test_crossed_deactivations_leave_one_active_admin(
    admin_database: None,  # noqa: ARG001
) -> None:
    first_admin = await seed_admin()
    second_admin = await seed_admin(username="second", telegram_id=2002)

    async with (
        app_client([admin_module]) as first,
        app_client([admin_module]) as second,
    ):
        responses = await asyncio.gather(
            first.post(
                f"/admin/admins/{second_admin.id}/deactivate",
                headers=authorization(first_admin),
            ),
            second.post(
                f"/admin/admins/{first_admin.id}/deactivate",
                headers=authorization(second_admin),
            ),
        )

    assert sorted(response.status_code for response in responses) == [
        HTTPStatus.OK,
        HTTPStatus.UNAUTHORIZED,
    ]
    async with session_module.session_factory() as session:
        active = list((await session.scalars(select(Admin.id).where(Admin.is_active))).all())
    assert len(active) == 1


async def test_deactivation_revokes_target_credentials(http: AsyncClient) -> None:
    root = await seed_admin()
    target = await seed_admin(username="target", telegram_id=2002)
    target_login = await login(http, username="target")

    response = await http.post(
        f"/admin/admins/{target.id}/deactivate",
        headers=authorization(root),
    )
    target_current = await http.get(
        "/admin/admins/me",
        headers={"authorization": f"Bearer {target_login.json()['access_token']}"},
    )
    target_refresh = await http.post("/admin/auth/refresh")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["is_active"] is False
    assert target_current.status_code == HTTPStatus.UNAUTHORIZED
    assert target_refresh.status_code == HTTPStatus.UNAUTHORIZED


async def test_bootstrap_is_locked_and_idempotent(admin_database: None) -> None:  # noqa: ARG001
    settings = AdminSettings(
        bootstrap_username="Initial.Admin",
        bootstrap_password=SecretStr(PASSWORD),
        bootstrap_telegram_id=4242,
    )

    first, second = await asyncio.gather(
        bootstrap_first_admin(
            session_factory=session_module.session_factory,
            settings=settings,
        ),
        bootstrap_first_admin(
            session_factory=session_module.session_factory,
            settings=settings,
        ),
    )

    assert sum(created is not None for created in (first, second)) == 1
    async with session_module.session_factory() as session:
        admins = list((await session.scalars(select(Admin))).all())
    assert len(admins) == 1
    assert admins[0].username == "initial.admin"
    assert verify_password(PASSWORD, admins[0].hashed_password)


async def test_bootstrap_fails_safely_without_credentials(admin_database: None) -> None:  # noqa: ARG001
    settings = AdminSettings(bootstrap_username="", bootstrap_password=SecretStr(""))

    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_USERNAME"):
        await bootstrap_first_admin(
            session_factory=session_module.session_factory,
            settings=settings,
        )


async def test_bootstrap_does_not_require_credentials_after_first_admin(
    admin_database: None,  # noqa: ARG001
) -> None:
    await seed_admin()

    created = await bootstrap_first_admin(
        session_factory=session_module.session_factory,
        settings=AdminSettings(
            bootstrap_username="",
            bootstrap_password=SecretStr(""),
        ),
    )

    assert created is None


async def test_lifespan_bootstraps_from_admin_settings(admin_database: None) -> None:  # noqa: ARG001
    settings = AdminSettings(
        bootstrap_username="startup",
        bootstrap_password=SecretStr(PASSWORD),
    )
    module = replace(admin_module, lifespan=admin_lifespan(settings=settings))

    async with app_client([module], lifespan=True) as client:
        response = await login(client, username="startup")

    assert response.status_code == HTTPStatus.OK


def test_admin_settings_are_read_from_an_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ADMIN_BOOTSTRAP_USERNAME=from-env\n"
        f"ADMIN_BOOTSTRAP_PASSWORD={PASSWORD}\n"
        "ADMIN_BOOTSTRAP_TELEGRAM_ID=777\n",
        encoding="utf-8",
    )

    loaded = AdminSettings(_env_file=env_file)

    assert loaded.bootstrap_username == "from-env"
    assert loaded.bootstrap_password.get_secret_value() == PASSWORD
    assert loaded.bootstrap_telegram_id == 777


def test_admin_settings_reject_an_insecure_production_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.admin.services.settings.settings.app_env",
        "prod",
    )

    with pytest.raises(ValueError, match="must be true in production"):
        AdminSettings(refresh_cookie_secure=False)


def test_admin_settings_require_secure_for_samesite_none() -> None:
    with pytest.raises(ValueError, match="SameSite=None"):
        AdminSettings(
            refresh_cookie_secure=False,
            refresh_cookie_samesite="none",
        )


async def test_cleanup_removes_only_expired_refresh_tokens(http: AsyncClient) -> None:
    await seed_admin()
    await login(http)
    now = datetime.now(tz=UTC)
    async with session_module.session_factory() as session, session.begin():
        existing = list((await session.scalars(select(AdminRefreshToken))).all())
        existing[0].expires_at = now - timedelta(seconds=1)
        future = AdminRefreshToken(
            id=uuid4(),
            admin_id=existing[0].admin_id,
            family_id=uuid4(),
            token_hash="f" * 64,
            auth_version=1,
            expires_at=now + timedelta(hours=1),
        )
        session.add(future)

    purged = await purge_expired_refresh_tokens(
        session_factory=session_module.session_factory,
        now=now,
    )

    assert purged == 1
    async with session_module.session_factory() as session:
        remaining = list((await session.scalars(select(AdminRefreshToken.id))).all())
    assert remaining == [future.id]


def test_admin_model_has_the_required_keyset_index() -> None:
    table = cast(Table, Admin.__table__)
    index = next(item for item in table.indexes if item.name == "ix_admins_keyset")

    assert [str(expression) for expression in index.expressions] == [
        "admins.created_at DESC",
        "admins.id DESC",
    ]
