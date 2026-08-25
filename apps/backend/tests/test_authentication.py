"""Точечная Bearer-аутентификация HTTP-ручек."""

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Final
from uuid import UUID

import pytest
from fastapi import APIRouter
from httpx import AsyncClient

from app.kernel.context import actor_id
from app.kernel.registry import Module
from app.kernel.security.authentication import authenticated, is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from tests.asgi import app_client

ADMIN: Final = UUID(int=91)


def authentication_module() -> Module:
    """Публичная и защищённая ручки для проверки точечной политики."""
    router = APIRouter()

    @router.get("/public")
    async def public() -> dict[str, str]:
        return {"access": "public"}

    @router.get("/protected")
    @authenticated
    async def protected() -> dict[str, str]:
        return {"actor": str(actor_id.get())}

    return Module(name="authentication", router=router, prefix="")


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    async with app_client([authentication_module()]) as client:
        yield client


def bearer(*, kind: str = "admin") -> dict[str, str]:
    """Выпустить access JWT с указанным видом субъекта."""
    token = issue_tokens(ADMIN, settings=jwt_settings, claims={"kind": kind}).access_token
    return {"authorization": f"Bearer {token}"}


def test_the_marker_does_not_wrap_the_function() -> None:
    async def endpoint() -> None: ...

    marked = authenticated(endpoint)

    assert marked is endpoint
    assert is_authenticated(endpoint)


async def test_public_route_stays_public(http: AsyncClient) -> None:
    response = await http.get("/public")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"access": "public"}


async def test_protected_route_requires_a_token(http: AsyncClient) -> None:
    response = await http.get("/protected")

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["reason"] == "missing-token"


async def test_admin_access_reaches_the_actor_context(http: AsyncClient) -> None:
    response = await http.get("/protected", headers=bearer())

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"actor": str(ADMIN)}


async def test_another_actor_kind_is_rejected(http: AsyncClient) -> None:
    response = await http.get("/protected", headers=bearer(kind="courier"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["reason"] == "wrong-actor-kind"


async def test_refresh_is_not_accepted_as_access(http: AsyncClient) -> None:
    refresh = issue_tokens(ADMIN, settings=jwt_settings).refresh_token

    response = await http.get(
        "/protected",
        headers={"authorization": f"Bearer {refresh}"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["reason"] == "wrong-token-type"
