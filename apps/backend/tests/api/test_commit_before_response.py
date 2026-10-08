"""Клиент не получает 2xx, если транзакция запроса не закоммитилась.

Проверяется порядок «коммит → ответ». Держится он на объявлении зависимости
транзакции: `Depends(get_uow, scope="function")` в `app.api.deps`. С областью
по умолчанию (`request`) FastAPI закрывает зависимость уже после отправки
ответа, и упавший коммит достаётся клиенту как успех, а исключение уходит
только в лог.

Почему настоящий uvicorn, а не `ASGITransport`. Транспорт httpx собирает ответ
целиком и лишь потом решает судьбу исключения, случившегося после его
отправки: при `raise_app_exceptions=True` тест увидит исключение, при `False` —
тот же 200, что и в исправном случае. То есть на нём «клиент уже получил 2xx»
неотличимо от «клиент получил 500», а проверяется здесь ровно это различие.

Почему отложенное ограничение, а не подменённый `commit`. Так ломается именно
коммит, и ломается тем же способом, что и в проде: нарушение
`DEFERRABLE INITIALLY DEFERRED` Postgres обнаруживает в момент `COMMIT`, а не
на `INSERT`. Подмена метода проверяла бы нашу заглушку.
"""

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any, Final

import pytest
from fastapi import APIRouter
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import Uow
from app.kernel.db import session as session_module
from app.kernel.db.crud import CRUD
from app.kernel.idempotency import IDEMPOTENCY_KEY_HEADER, IdempotencyKey, idempotent
from app.kernel.registry import Module
from tests.asgi import app_client
from tests.models import Widget
from tests.schemas import WidgetCreate, WidgetResponse

#: Имя, по которому ломается коммит: строка с ним уже лежит в таблице.
CLASH: Final = "clash"
KEY: Final = "commit-key-0001"
CONSTRAINT: Final = "uq_test_widgets_name_deferred"
BODY: Final[dict[str, Any]] = {"name": CLASH, "quantity": 1}


def widgets_module() -> Module:
    """Две ручки, создающие строку в транзакции запроса: обычная и с ключом."""
    router = APIRouter()

    @router.post("/widgets", status_code=HTTPStatus.CREATED)
    async def create_widget(body: WidgetCreate, uow: Uow) -> WidgetResponse:
        widget = await CRUD.create(Widget, body, uow)
        return WidgetResponse.model_validate(widget)

    @router.post("/widgets/keyed", status_code=HTTPStatus.CREATED)
    @idempotent
    async def create_widget_with_key(body: WidgetCreate, uow: Uow) -> WidgetResponse:
        widget = await CRUD.create(Widget, body, uow)
        return WidgetResponse.model_validate(widget)

    return Module(name="widgets", router=router, prefix="")


@pytest.fixture
async def failing_commit(database: AsyncEngine, clean_db: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Занятое имя и отложенное ограничение на него.

    После этого `INSERT` со значением `CLASH` проходит, а `COMMIT` — нет.
    Ограничение снимается на выходе: остальные тесты работают с той же
    таблицей и о нём не знают.
    """
    async with database.begin() as conn:
        await conn.execute(
            text(
                f"ALTER TABLE {Widget.__tablename__} ADD CONSTRAINT {CONSTRAINT} "
                "UNIQUE (name) DEFERRABLE INITIALLY DEFERRED"
            )
        )
    async with session_module.session_factory() as session, session.begin():
        await CRUD.create(Widget, WidgetCreate(name=CLASH), session)

    yield

    async with database.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {Widget.__tablename__} DROP CONSTRAINT {CONSTRAINT}"))


@pytest.fixture
async def live() -> AsyncIterator[AsyncClient]:
    """Клиент к приложению, поднятому настоящим сервером."""
    async with app_client([widgets_module()], live=True) as client:
        yield client


async def count_widgets() -> int:
    async with session_module.session_factory() as db:
        return (await db.execute(select(func.count()).select_from(Widget))).scalar_one()


async def stored_keys() -> list[IdempotencyKey]:
    async with session_module.session_factory() as db:
        return list((await db.scalars(select(IdempotencyKey))).all())


@pytest.mark.usefixtures("clean_db")
async def test_a_committed_request_answers_normally(live: AsyncClient) -> None:
    """Страховка от теста, который зелен потому, что сервер вообще не отвечает."""
    response = await live.post("/widgets", json={"name": "fine", "quantity": 1})

    assert response.status_code == HTTPStatus.CREATED
    assert await count_widgets() == 1


@pytest.mark.usefixtures("failing_commit")
async def test_a_failed_commit_is_not_answered_with_success(live: AsyncClient) -> None:
    """Главный инвариант: не закоммитилось — значит не 2xx."""
    response = await live.post("/widgets", json=BODY)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == HTTPStatus.INTERNAL_SERVER_ERROR
    # Строка в таблице ровно одна — та, что положила фикстура.
    assert await count_widgets() == 1


@pytest.mark.usefixtures("failing_commit")
async def test_a_failed_commit_leaves_no_key_reserved(live: AsyncClient) -> None:
    """Откат уносит ключ вместе с данными, поэтому повтор возможен тем же ключом."""
    response = await live.post(
        "/widgets/keyed",
        json=BODY,
        headers={IDEMPOTENCY_KEY_HEADER: KEY},
    )

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert await stored_keys() == []
    assert await count_widgets() == 1
