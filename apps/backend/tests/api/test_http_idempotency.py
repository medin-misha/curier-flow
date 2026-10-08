"""Идемпотентность записи: повтор, конфликт, гонка и уборка ключей.

Приложение собирается фабрикой `create_app` с тестовым модулем: ручка, которая
действительно создаёт строку, нужна для всех проверок сразу, а заводить её в
продуктовом модуле ради тестов нельзя.

Postgres настоящий: гарантия держится на `INSERT ... ON CONFLICT DO NOTHING`
и на том, что параллельная транзакция ждёт исхода соседней. На другом диалекте
проверялся бы не тот механизм.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import func, select, update
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.api.deps import Actor, Uow
from app.kernel.db import session as session_module
from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict
from app.kernel.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    MAX_KEY_LENGTH,
    IdempotencyKey,
    IdempotencyStatus,
    idempotent,
    is_idempotent,
    purge_expired_keys,
)
from app.kernel.registry import Module
from app.kernel.security.tokens import issue_tokens, jwt_settings
from tests.asgi import app_client
from tests.models import Widget
from tests.schemas import WidgetCreate, WidgetResponse

pytestmark = pytest.mark.usefixtures("clean_db")

KEY: Final = "test-key-0001"
BOLT: Final[dict[str, Any]] = {"name": "bolt", "quantity": 1}


def widgets_module(*, delay: float = 0.0) -> Module:
    """Модуль с ручками, на которых проверяется идемпотентность.

    `delay` держит транзакцию открытой: без задержки два «параллельных»
    запроса успевают выполниться по очереди, и гонка не воспроизводится.
    """
    router = APIRouter()

    @router.post("/widgets", status_code=HTTPStatus.CREATED)
    @idempotent
    async def create_widget(body: WidgetCreate, uow: Uow, actor: Actor) -> WidgetResponse:
        await asyncio.sleep(delay)
        widget = await CRUD.create(Widget, body, uow, owner="system" if actor is None else "user")
        return WidgetResponse.model_validate(widget)

    @router.post("/widgets/broken", status_code=HTTPStatus.CREATED)
    @idempotent
    async def create_and_fail(body: WidgetCreate, uow: Uow) -> WidgetResponse:
        widget = await CRUD.create(Widget, body, uow)
        raise Conflict("Business rule says no", widget=str(widget.id))

    @router.post("/widgets/plain", status_code=HTTPStatus.CREATED)
    async def create_without_key(body: WidgetCreate, uow: Uow) -> WidgetResponse:
        widget = await CRUD.create(Widget, body, uow)
        return WidgetResponse.model_validate(widget)

    @router.post("/widgets/rejected")
    @idempotent
    async def reject_politely() -> Response:
        """Ошибка, отданная ответом, а не исключением: транзакция коммитится."""
        return JSONResponse({"detail": "not today"}, status_code=HTTPStatus.PAYMENT_REQUIRED)

    @router.post("/widgets/streamed")
    @idempotent
    async def stream_something() -> StreamingResponse:
        """Ответ, тела которого на момент сохранения ещё не существует."""
        return StreamingResponse(iter([b"chunk"]), media_type="text/plain")

    return Module(name="widgets", router=router, prefix="")


async def client(*, delay: float = 0.0) -> AsyncIterator[AsyncClient]:
    """Клиент к приложению с тестовым модулем."""
    async with app_client([widgets_module(delay=delay)]) as http:
        yield http


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    async for opened in client():
        yield opened


async def count_widgets() -> int:
    async with session_module.session_factory() as db:
        return (await db.execute(select(func.count()).select_from(Widget))).scalar_one()


async def stored_keys() -> list[IdempotencyKey]:
    async with session_module.session_factory() as db:
        return list((await db.scalars(select(IdempotencyKey))).all())


async def test_the_same_key_and_body_return_the_stored_response(http: AsyncClient) -> None:
    """Главный сценарий: клиент повторил запрос, сущность создана одна."""
    first = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})
    second = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert first.status_code == HTTPStatus.CREATED
    assert second.status_code == first.status_code
    assert second.content == first.content
    assert second.headers["content-type"] == first.headers["content-type"]
    assert second.headers["idempotency-replayed"] == "true"
    assert "idempotency-replayed" not in first.headers
    assert await count_widgets() == 1


async def test_the_replayed_response_carries_a_fresh_request_id(http: AsyncClient) -> None:
    """Иначе разбор инцидента ушёл бы в логи чужого, давно прошедшего запроса."""
    first = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})
    second = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert second.headers["x-request-id"] != first.headers["x-request-id"]


async def test_the_same_key_with_a_different_body_is_a_conflict(http: AsyncClient) -> None:
    await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})
    response = await http.post(
        "/widgets",
        json={"name": "nut", "quantity": 2},
        headers={IDEMPOTENCY_KEY_HEADER: KEY},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["reason"] == "payload-mismatch"
    assert await count_widgets() == 1


async def test_the_same_key_on_another_path_is_a_conflict(http: AsyncClient) -> None:
    """Ключ повторяют для повтора запроса, а не для другой операции."""
    await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})
    response = await http.post("/widgets/broken", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["reason"] == "payload-mismatch"


async def test_the_same_key_from_another_actor_is_a_conflict(http: AsyncClient) -> None:
    """Ключи придумывают клиенты: чужой ключ не должен отдавать чужой ответ."""
    mine = issue_tokens(uuid4(), settings=jwt_settings).access_token
    theirs = issue_tokens(uuid4(), settings=jwt_settings).access_token

    first = await http.post(
        "/widgets",
        json=BOLT,
        headers={IDEMPOTENCY_KEY_HEADER: KEY, "authorization": f"Bearer {mine}"},
    )
    second = await http.post(
        "/widgets",
        json=BOLT,
        headers={IDEMPOTENCY_KEY_HEADER: KEY, "authorization": f"Bearer {theirs}"},
    )

    assert first.status_code == HTTPStatus.CREATED
    assert second.status_code == HTTPStatus.CONFLICT
    assert second.json()["reason"] == "payload-mismatch"


async def test_the_key_row_is_committed_with_the_data(http: AsyncClient) -> None:
    """Откат обязан уносить ключ вместе с данными.

    Иначе после сорвавшегося запроса ключ остался бы занят строкой, к которой
    не привязано ничего: клиент не может ни получить ответ, ни повторить
    попытку.
    """
    failed = await http.post("/widgets/broken", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert failed.status_code == HTTPStatus.CONFLICT
    assert await count_widgets() == 0
    assert await stored_keys() == []


async def test_a_failed_request_may_be_retried_with_the_same_key(http: AsyncClient) -> None:
    """Ключ освобождается ошибкой: повторить сорвавшуюся операцию — это норма."""
    await http.post("/widgets/broken", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})
    retried = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert retried.status_code == HTTPStatus.CREATED
    assert await count_widgets() == 1


async def test_a_parallel_repeat_is_rejected_while_the_first_request_runs() -> None:
    """Второй запрос приходит, пока первый ещё в транзакции.

    Ответа под ключом в этот момент ещё нет, поэтому вернуть нечего: второй
    получает 409 и повторяет попытку позже — тогда он уже получит сохранённый
    ответ.
    """
    async for http in client(delay=0.3):
        headers = {IDEMPOTENCY_KEY_HEADER: KEY}
        first, second = await asyncio.gather(
            http.post("/widgets", json=BOLT, headers=headers),
            http.post("/widgets", json=BOLT, headers=headers),
        )

        statuses = sorted(response.status_code for response in (first, second))
        assert statuses == [HTTPStatus.CREATED, HTTPStatus.CONFLICT]
        rejected = first if first.status_code == HTTPStatus.CONFLICT else second
        assert rejected.json()["reason"] == "in-flight"
        assert await count_widgets() == 1

        later = await http.post("/widgets", json=BOLT, headers=headers)
        assert later.status_code == HTTPStatus.CREATED
        assert later.headers["idempotency-replayed"] == "true"
        assert await count_widgets() == 1


async def test_the_key_header_is_required_on_a_marked_route(http: AsyncClient) -> None:
    """Ручка обещает защиту от повтора, а без ключа выдать её невозможно."""
    response = await http.post("/widgets", json=BOLT)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["header"] == IDEMPOTENCY_KEY_HEADER
    assert await count_widgets() == 0


async def test_an_overlong_key_is_rejected(http: AsyncClient) -> None:
    """Иначе длиной строки в нашей таблице управляет клиент."""
    response = await http.post(
        "/widgets",
        json=BOLT,
        headers={IDEMPOTENCY_KEY_HEADER: "k" * (MAX_KEY_LENGTH + 1)},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await count_widgets() == 0


async def test_unmarked_routes_are_untouched(http: AsyncClient) -> None:
    """Идемпотентность включается осознанно, а не на всё приложение сразу."""
    first = await http.post("/widgets/plain", json=BOLT)
    second = await http.post("/widgets/plain", json=BOLT)

    assert (first.status_code, second.status_code) == (HTTPStatus.CREATED, HTTPStatus.CREATED)
    assert await count_widgets() == 2
    assert await stored_keys() == []


async def test_the_stored_row_holds_the_whole_answer(http: AsyncClient) -> None:
    """Статус и заголовки хранятся рядом с телом: без них повтор не совпадёт."""
    response = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    (row,) = await stored_keys()
    assert row.status is IdempotencyStatus.COMPLETED
    assert row.response_status == HTTPStatus.CREATED
    assert row.response_body == response.content
    assert row.response_headers is not None
    assert row.response_headers["content-type"] == "application/json"
    # Заголовки конкретной передачи не сохраняются: длину пересчитает сервер,
    # а чужой идентификатор запроса увёл бы разбор инцидента не туда.
    assert "content-length" not in row.response_headers
    assert "x-request-id" not in row.response_headers


async def test_the_header_is_documented_in_the_schema(http: AsyncClient) -> None:
    """Страховка: если обвязка не встала на маршрут, ключ не окажется в схеме."""
    schema = (await http.get("/openapi.json")).json()

    parameters = schema["paths"]["/widgets"]["post"]["parameters"]
    key_parameter = next(item for item in parameters if item["name"] == IDEMPOTENCY_KEY_HEADER)
    assert key_parameter["in"] == "header"
    assert key_parameter["required"] is True
    assert "parameters" not in schema["paths"]["/widgets/plain"]["post"]


async def test_purge_removes_expired_keys_only() -> None:
    """Уборка чистит по возрасту и не трогает свежие ключи."""
    async with session_module.session_factory() as db, db.begin():
        db.add_all(
            [
                IdempotencyKey(key="old", request_hash="x", status=IdempotencyStatus.COMPLETED),
                IdempotencyKey(key="new", request_hash="y", status=IdempotencyStatus.COMPLETED),
            ]
        )
    async with session_module.session_factory() as db, db.begin():
        await db.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.key == "old")
            .values(created_at=datetime.now(tz=UTC) - timedelta(days=2))
        )

    deleted = await purge_expired_keys(
        session_factory=session_module.session_factory,
        retention=timedelta(hours=24),
    )

    assert deleted == 1
    assert [row.key for row in await stored_keys()] == ["new"]


async def test_purge_is_safe_to_run_twice(http: AsyncClient) -> None:
    """Периодическая задача обязана переживать параллельный запуск."""
    await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    passes = await asyncio.gather(
        *(
            purge_expired_keys(
                session_factory=session_module.session_factory,
                retention=timedelta(seconds=0),
            )
            for _ in range(3)
        )
    )

    assert sum(passes) == 1
    assert await stored_keys() == []


async def test_an_error_response_releases_the_key(http: AsyncClient) -> None:
    """Ошибка, отданная ответом, ключ тоже не занимает: повтор должен быть возможен."""
    first = await http.post("/widgets/rejected", headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert first.status_code == HTTPStatus.PAYMENT_REQUIRED
    assert await stored_keys() == []

    second = await http.post("/widgets/rejected", headers={IDEMPOTENCY_KEY_HEADER: KEY})
    assert second.status_code == HTTPStatus.PAYMENT_REQUIRED
    assert "idempotency-replayed" not in second.headers


async def test_a_streaming_response_is_not_replayed(http: AsyncClient) -> None:
    """Тела потокового ответа на момент сохранения ещё нет — воспроизводить нечего."""
    first = await http.post("/widgets/streamed", headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert first.content == b"chunk"
    (row,) = await stored_keys()
    assert row.status is IdempotencyStatus.IN_PROGRESS

    second = await http.post("/widgets/streamed", headers={IDEMPOTENCY_KEY_HEADER: KEY})
    assert second.status_code == HTTPStatus.CONFLICT
    assert second.json()["reason"] == "in-progress"


async def test_assembling_the_same_module_twice_is_harmless() -> None:
    """Реестр модулей один, а приложение за процесс собирают не раз (тесты, скрипты)."""
    module = widgets_module()

    async with app_client([module]) as first, app_client([module]) as _:
        response = await first.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert response.status_code == HTTPStatus.CREATED
    assert await count_widgets() == 1


def test_the_mark_travels_with_the_endpoint() -> None:
    """Страховка от проверки, которая ничего не проверяет."""
    router = widgets_module().router
    assert router is not None

    marked = {
        route.path
        for route in router.routes
        if isinstance(route, APIRoute) and is_idempotent(route.endpoint)
    }
    assert marked == {"/widgets", "/widgets/broken", "/widgets/rejected", "/widgets/streamed"}


async def test_the_actor_of_a_replayed_request_is_not_reused(http: AsyncClient) -> None:
    """Сохранённый ответ принадлежит своему актору, а не тому, кто пришёл позже."""
    token = issue_tokens(UUID(int=7), settings=jwt_settings).access_token
    authorized = {IDEMPOTENCY_KEY_HEADER: KEY, "authorization": f"Bearer {token}"}

    created = await http.post("/widgets", json=BOLT, headers=authorized)
    anonymous = await http.post("/widgets", json=BOLT, headers={IDEMPOTENCY_KEY_HEADER: KEY})

    assert created.json()["owner"] == "user"
    assert anonymous.status_code == HTTPStatus.CONFLICT
