"""Зависимости HTTP-слоя: границы транзакции, страница и действующее лицо."""

from collections.abc import AsyncIterator, Callable
from http import HTTPStatus
from typing import Any, ClassVar, Final, get_args
from uuid import UUID, uuid4

import pytest
from fastapi import APIRouter
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, CurrentActor, PageQuery, RoSession, Uow
from app.kernel.context import actor_id
from app.kernel.db import session as session_module
from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.events.bus import DomainEvent, emit
from app.kernel.events.models import OutboxMessage
from app.kernel.pagination import PageParams
from app.kernel.registry import Module
from app.kernel.security.tokens import issue_tokens, jwt_settings
from tests.asgi import app_client

ACTOR: Final = UUID(int=17)


class ThingHappened(DomainEvent):
    """Событие, по заголовкам которого проверяется контекст операции."""

    topic: ClassVar[str] = "test.thing_happened"

    thing: str


def actors_module() -> Module:
    """Три ручки: с необязательным актором, с обязательным и с событием."""
    router = APIRouter()

    @router.get("/anyone")
    async def anyone(actor: Actor) -> dict[str, str | None]:
        return {"actor": None if actor is None else str(actor), "context": str(actor_id.get())}

    @router.get("/members")
    async def members(actor: CurrentActor) -> dict[str, str]:
        return {"actor": str(actor)}

    @router.post("/things")
    async def create_thing(actor: CurrentActor, uow: Uow) -> dict[str, str]:
        emit(uow, ThingHappened(thing="widget"))
        return {"actor": str(actor)}

    @router.get("/page")
    async def page(params: PageQuery) -> dict[str, str | int | None]:
        return {"cursor": params.cursor, "limit": params.limit}

    return Module(name="actors", router=router, prefix="")


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    async with app_client([actors_module()]) as client:
        yield client


def bearer(subject: UUID = ACTOR) -> dict[str, str]:
    """Заголовок с годным access-токеном."""
    token = issue_tokens(subject, settings=jwt_settings).access_token
    return {"authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("alias", "expected"),
    [(Uow, get_uow), (RoSession, get_ro_session)],
)
def test_alias_binds_the_expected_session_dependency(
    alias: Any,
    expected: Callable[..., Any],
) -> None:
    """Подмена `Uow` на читающую сессию отменила бы коммит во всех ручках сразу."""
    session_type, depends = get_args(alias)

    assert session_type is AsyncSession
    assert depends.dependency is expected


def test_the_write_transaction_closes_before_the_response_is_sent() -> None:
    """Область по умолчанию закрывает зависимость уже после отправки ответа.

    То есть упавший коммит уехал бы клиенту как 2xx. Что этого не происходит,
    доказывает `tests/test_commit_before_response.py` на настоящем сервере;
    здесь — дешёвая страховка от случайного снятия области при правке.
    """
    _, depends = get_args(Uow)

    assert depends.scope == "function"


def test_page_query_binds_the_kernel_schema() -> None:
    schema, _ = get_args(PageQuery)

    assert schema is PageParams


async def test_page_query_reads_the_query_string(http: AsyncClient) -> None:
    response = await http.get("/page", params={"limit": 3})

    assert response.json() == {"cursor": None, "limit": 3}


async def test_a_request_without_a_token_is_anonymous(http: AsyncClient) -> None:
    """Модуля авторизации в шаблоне нет: анонимный вызов — это норма, а не 401."""
    response = await http.get("/anyone")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"actor": None, "context": "None"}


async def test_a_valid_token_reaches_the_context(http: AsyncClient) -> None:
    response = await http.get("/anyone", headers=bearer())

    assert response.json() == {"actor": str(ACTOR), "context": str(ACTOR)}


@pytest.mark.parametrize(
    "authorization",
    ["Bearer nonsense", "Basic dXNlcjpwYXNz", "Bearer ", "nonsense"],
)
async def test_a_broken_token_is_unauthorized(http: AsyncClient, authorization: str) -> None:
    """Испорченный токен — это 401, а не молчаливая анонимность."""
    response = await http.get("/anyone", headers={"authorization": authorization})

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_refresh_token_is_not_accepted_by_the_api(http: AsyncClient) -> None:
    """Refresh живёт неделями и ходит в одну ручку обновления, а не во все."""
    refresh = issue_tokens(ACTOR, settings=jwt_settings).refresh_token

    response = await http.get("/anyone", headers={"authorization": f"Bearer {refresh}"})

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["reason"] == "wrong-token-type"


async def test_a_protected_route_requires_a_token(http: AsyncClient) -> None:
    """Требование авторизации — одна строка в сигнатуре ручки (`CurrentActor`)."""
    anonymous = await http.get("/members")
    authorized = await http.get("/members", headers=bearer())

    assert anonymous.status_code == HTTPStatus.UNAUTHORIZED
    assert anonymous.json()["reason"] == "missing-token"
    assert authorized.status_code == HTTPStatus.OK
    assert authorized.json() == {"actor": str(ACTOR)}


@pytest.mark.usefixtures("clean_db")
async def test_the_actor_reaches_the_headers_of_an_emitted_event(http: AsyncClient) -> None:
    """Иначе по событию не восстановить, кто именно его вызвал."""
    subject = uuid4()

    response = await http.post("/things", headers=bearer(subject))

    assert response.status_code == HTTPStatus.OK
    async with session_module.session_factory() as db:
        (message,) = (await db.scalars(select(OutboxMessage))).all()
    assert message.topic == ThingHappened.topic
    assert message.headers["actor_id"] == str(subject)
    assert message.headers["request_id"] == response.headers["x-request-id"]
