"""Шина событий: запись в outbox, привязка к транзакции, хуки после коммита."""

import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar
from uuid import UUID, uuid4

import pytest
from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Uow
from app.kernel.context import actor_id, request_id
from app.kernel.db import session as session_module
from app.kernel.db.session import AFTER_COMMIT_HOOKS, AfterCommitHook, get_uow
from app.kernel.events.bus import DomainEvent, after_commit, emit, topic_of
from app.kernel.events.models import OutboxMessage
from app.kernel.registry import Module
from tests.asgi import app_client
from tests.logs import capture_logs

uow = asynccontextmanager(get_uow)


class OrderCreated(DomainEvent):
    """Событие со всеми типами, которых нет в JSON."""

    topic: ClassVar[str] = "order.created"

    order_id: UUID
    placed_at: datetime
    total: Decimal


class OrderShipped(DomainEvent):
    """Второе событие: нужно там, где проверяется порядок записей."""

    topic: ClassVar[str] = "order.shipped"

    order_id: UUID


class Untopiced(DomainEvent):
    """Событие, автор которого забыл объявить топик."""

    order_id: UUID


def _order_created() -> OrderCreated:
    return OrderCreated(
        order_id=uuid4(),
        placed_at=datetime(2026, 4, 1, 10, 30, 15, 123456, tzinfo=UTC),
        total=Decimal("1099.99"),
    )


async def _outbox_rows() -> list[OutboxMessage]:
    """Строки outbox отдельной сессией: то, что реально доехало до базы."""
    async with session_module.session_factory() as fresh:
        rows = await fresh.scalars(
            select(OutboxMessage).order_by(OutboxMessage.occurred_at, OutboxMessage.id)
        )
        return list(rows)


async def _outbox_count() -> int:
    async with session_module.session_factory() as fresh:
        return await fresh.scalar(select(func.count()).select_from(OutboxMessage)) or 0


def test_emit_is_not_a_coroutine_function() -> None:
    """`emit` обязан быть синхронным: у него не должно быть точек ожидания."""
    assert not inspect.iscoroutinefunction(emit)


@pytest.mark.usefixtures("clean_db")
async def test_emit_only_stages_the_row(session: AsyncSession) -> None:
    """До коммита событие живёт в сессии и в базу не ходит."""
    emit(session, _order_created())

    pending = list(session.new)
    assert len(pending) == 1
    staged = pending[0]
    assert isinstance(staged, OutboxMessage)
    # id проставляет Python-дефолт колонки в момент flush: он всё ещё пуст,
    # значит ни одного запроса в базу отправлено не было.
    assert staged.id is None
    assert await _outbox_count() == 0


@pytest.mark.usefixtures("clean_db")
async def test_commit_leaves_exactly_one_unpublished_row() -> None:
    event = _order_created()

    async with uow() as session:
        emit(session, event)

    rows = await _outbox_rows()
    assert len(rows) == 1
    assert rows[0].topic == "order.created"
    assert rows[0].published_at is None
    assert rows[0].attempts == 0
    assert rows[0].last_error is None


@pytest.mark.usefixtures("clean_db")
async def test_rollback_takes_the_event_with_it() -> None:
    """Главный смысл outbox: событие не переживает откат своей транзакции."""
    with pytest.raises(RuntimeError, match="boom"):
        async with uow() as session:
            emit(session, _order_created())
            raise RuntimeError("boom")

    assert await _outbox_count() == 0


@pytest.mark.usefixtures("clean_db")
async def test_payload_survives_a_round_trip_through_jsonb() -> None:
    """datetime, UUID и Decimal обязаны восстанавливаться без потерь."""
    event = _order_created()

    async with uow() as session:
        emit(session, event)

    payload = (await _outbox_rows())[0].payload
    assert isinstance(payload["total"], str), "Decimal обязан ехать строкой, а не float"
    assert OrderCreated.model_validate(payload) == event


@pytest.mark.usefixtures("clean_db")
async def test_headers_carry_request_id_from_context() -> None:
    token = request_id.set("req-42")
    try:
        async with uow() as session:
            emit(session, _order_created())
    finally:
        request_id.reset(token)

    headers = (await _outbox_rows())[0].headers
    assert headers["request_id"] == "req-42"
    assert "actor_id" not in headers


@pytest.mark.usefixtures("clean_db")
async def test_headers_carry_actor_when_it_is_known() -> None:
    actor = uuid4()
    token = actor_id.set(actor)
    try:
        async with uow() as session:
            emit(session, _order_created())
    finally:
        actor_id.reset(token)

    assert (await _outbox_rows())[0].headers["actor_id"] == str(actor)


@pytest.mark.usefixtures("clean_db")
async def test_events_of_one_transaction_keep_their_order() -> None:
    """`occurred_at` не убывает, а порядок доразрешается первичным ключом.

    Строгого возрастания не требуем: `datetime.now()` имеет разрешение в
    микросекунду, и два соседних вызова регулярно попадают в одну и ту же
    метку. Порядок восстанавливает пара `(occurred_at, id)` — по ней же идёт
    выборка релея, а UUIDv7 монотонен по времени генерации.
    """
    order_id = uuid4()

    async with uow() as session:
        emit(session, OrderCreated(order_id=order_id, placed_at=datetime.now(tz=UTC), total=1))
        emit(session, OrderShipped(order_id=order_id))

    rows = await _outbox_rows()
    assert [row.topic for row in rows] == ["order.created", "order.shipped"]
    assert rows[0].occurred_at <= rows[1].occurred_at
    assert (rows[0].occurred_at, rows[0].id) < (rows[1].occurred_at, rows[1].id)


def test_event_without_topic_is_reported_clearly() -> None:
    with pytest.raises(TypeError, match="Untopiced declares no topic"):
        topic_of(Untopiced)


@pytest.mark.usefixtures("clean_db")
async def test_emit_refuses_an_event_without_topic(session: AsyncSession) -> None:
    with pytest.raises(TypeError, match="declares no topic"):
        emit(session, Untopiced(order_id=uuid4()))

    assert not list(session.new)


@pytest.mark.usefixtures("clean_db")
async def test_hooks_run_after_commit_in_registration_order() -> None:
    """Хук видит уже закоммиченные данные — иначе он не «после коммита»."""
    done: list[str] = []
    event = _order_created()

    def record(name: str) -> AfterCommitHook:
        async def hook() -> None:
            done.append(name)

        return hook

    async def check_visibility() -> None:
        done.append(f"rows:{await _outbox_count()}")

    async with uow() as session:
        emit(session, event)
        after_commit(session, record("first"))
        after_commit(session, check_visibility)
        after_commit(session, record("last"))
        assert done == []

    assert done == ["first", "rows:1", "last"]


@pytest.mark.usefixtures("clean_db")
async def test_rolled_back_transaction_runs_no_hooks() -> None:
    done: list[str] = []

    async def hook() -> None:
        done.append("ran")

    with pytest.raises(RuntimeError, match="boom"):
        async with uow() as session:
            after_commit(session, hook)
            raise RuntimeError("boom")

    assert done == []


@pytest.mark.usefixtures("clean_db")
async def test_failing_hook_is_logged_and_does_not_stop_the_others() -> None:
    """Упавший хук — это запись в логе, а не потерянные соседние хуки."""
    done: list[str] = []

    async def broken() -> None:
        raise RuntimeError("cache is down")

    async def survivor() -> None:
        done.append("ran")

    with capture_logs() as stream:
        async with uow() as session:
            after_commit(session, broken)
            after_commit(session, survivor)

    assert done == ["ran"]
    logged = stream.getvalue()
    assert "after_commit.hook_failed" in logged
    assert "cache is down" in logged


@pytest.mark.usefixtures("clean_db")
async def test_failing_hook_does_not_break_the_response() -> None:
    """Ответ уже сформирован: упавший необязательный эффект его не отменяет."""
    router = APIRouter()
    attempted: list[str] = []

    async def broken() -> None:
        attempted.append("tried")
        raise RuntimeError("cache is down")

    @router.post("/orders")
    async def create_order(session: Uow) -> dict[str, str]:
        emit(session, _order_created())
        after_commit(session, broken)
        return {"status": "created"}

    orders = Module(name="orders", router=router, prefix="")
    async with app_client([orders]) as client:
        response = await client.post("/orders")

    assert attempted == ["tried"], "хук обязан был выполниться после ответа"

    assert response.status_code == 200
    assert response.json() == {"status": "created"}
    # Транзакция обязана была закоммититься до того, как хук упал.
    assert await _outbox_count() == 1


@pytest.mark.usefixtures("clean_db")
async def test_hooks_are_taken_out_of_the_session() -> None:
    """Выполненные хуки не остаются в сессии: второй проход их не повторит."""
    done: list[str] = []

    async def hook() -> None:
        done.append("ran")

    async with uow() as session:
        after_commit(session, hook)

    assert done == ["ran"]
    assert not session.info.get(AFTER_COMMIT_HOOKS)
