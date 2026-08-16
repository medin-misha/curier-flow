"""Релей outbox: публикация, отсрочка повторов, DLQ, параллельные воркеры.

Брокер здесь не нужен: публикация приходит релею колбэком, и подменить её
падающей функцией дешевле и надёжнее, чем гасить настоящий RabbitMQ посреди
прогона. Полный путь до брокера и обратно проверяет `test_domain_events.py`.

База нужна настоящая: весь смысл релея в `FOR UPDATE SKIP LOCKED`, а его
поведение — это поведение Postgres, а не нашего кода.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.kernel.db import session as session_module
from app.kernel.events.models import OutboxMessage
from app.kernel.events.outbox import (
    DOMAIN_EVENTS_TOPOLOGY,
    OutboxSettings,
    OutgoingEvent,
    Publish,
    purge_published_events,
    relay_outbox,
)
from tests.logs import capture_logs

pytestmark = pytest.mark.usefixtures("clean_db")


def make_settings(**overrides: Any) -> OutboxSettings:
    """Настройки релея для теста.

    Отсрочка по умолчанию нулевая: почти всем тестам нужен предсказуемый
    отбор, а не ожидание. Там, где проверяется сама отсрочка, она задаётся
    явно вместе с возрастом строки.
    """
    return OutboxSettings(**{"retry_base_delay": 0.0, "max_attempts": 3, **overrides})


def collector() -> tuple[list[OutgoingEvent], Publish]:
    """Колбэк публикации, складывающий отправленное в список."""
    sent: list[OutgoingEvent] = []

    async def publish(event: OutgoingEvent) -> None:
        sent.append(event)

    return sent, publish


def broken(message: str = "broker is down") -> Publish:
    """Колбэк недоступного брокера."""

    async def publish(_event: OutgoingEvent) -> None:
        raise RuntimeError(message)

    return publish


async def add_event(
    *,
    topic: str = "tests.thing.done",
    payload: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
    attempts: int = 0,
    published_at: datetime | None = None,
    last_error: str | None = None,
) -> UUID:
    """Положить строку в outbox напрямую.

    Мимо `emit()`: тесту нужны произвольные `occurred_at` и `attempts`, а
    подгонять их временем прогона значило бы проверять таймеры вместо релея.
    """
    row = OutboxMessage(
        topic=topic,
        payload=payload if payload is not None else {"name": "bolt"},
        headers=headers if headers is not None else {"request_id": "req-1"},
        occurred_at=occurred_at or datetime.now(tz=UTC),
        attempts=attempts,
        published_at=published_at,
        last_error=last_error,
    )
    async with session_module.session_factory() as db, db.begin():
        db.add(row)
    return row.id


async def fetch(message_id: UUID) -> OutboxMessage:
    """Строка outbox такой, какой её видит соседняя сессия."""
    async with session_module.session_factory() as db:
        return await db.get_one(OutboxMessage, message_id)


async def count_rows() -> int:
    async with session_module.session_factory() as db:
        result = await db.execute(select(func.count()).select_from(OutboxMessage))
        return result.scalar_one()


async def run_relay(
    publish: Publish,
    *,
    dead_letter: Publish | None = None,
    **overrides: Any,
) -> int:
    """Один проход релея поверх тестовой базы."""
    graveyard = dead_letter if dead_letter is not None else collector()[1]
    return await relay_outbox(
        session_factory=session_module.session_factory,
        publish=publish,
        dead_letter=graveyard,
        settings=make_settings(**overrides),
    )


def test_defaults_match_the_env_example() -> None:
    settings = OutboxSettings()

    assert settings.relay_interval == 5
    assert settings.batch_size == 100
    assert settings.max_attempts == 12
    assert settings.retry_base_delay == 5.0
    assert settings.retry_max_delay == 3600.0
    assert settings.retention_days == 7
    assert settings.cleanup_cron == "17 3 * * *"


def test_domain_topology_routes_every_topic() -> None:
    """Событие без подписчиков не должно выглядеть ошибкой публикации."""
    assert DOMAIN_EVENTS_TOPOLOGY.exchange == "domain.events"
    assert DOMAIN_EVENTS_TOPOLOGY.queue == "domain.events.subscribers"
    assert DOMAIN_EVENTS_TOPOLOGY.routing_key == "#"
    assert DOMAIN_EVENTS_TOPOLOGY.exchange_type == "topic"
    assert DOMAIN_EVENTS_TOPOLOGY.dead_letter


async def test_empty_outbox_publishes_nothing() -> None:
    sent, publish = collector()

    assert await run_relay(publish) == 0
    assert sent == []


async def test_row_is_published_and_marked() -> None:
    message_id = await add_event(topic="order.created", payload={"total": "10.50"})
    sent, publish = collector()

    assert await run_relay(publish) == 1

    assert [event.message_id for event in sent] == [message_id]
    assert sent[0].topic == "order.created"
    assert json.loads(sent[0].body) == {"total": "10.50"}
    assert sent[0].headers == {"request_id": "req-1"}

    row = await fetch(message_id)
    assert row.published_at is not None
    assert row.attempts == 0
    assert row.last_error is None


async def test_published_row_is_never_picked_again() -> None:
    await add_event()
    sent, publish = collector()

    assert await run_relay(publish) == 1
    assert await run_relay(publish) == 0
    assert len(sent) == 1


async def test_rows_leave_in_the_order_they_occurred() -> None:
    now = datetime.now(tz=UTC)
    first = await add_event(topic="a", occurred_at=now - timedelta(seconds=2))
    second = await add_event(topic="b", occurred_at=now - timedelta(seconds=1))
    sent, publish = collector()

    await run_relay(publish)

    assert [event.message_id for event in sent] == [first, second]


async def test_batch_size_limits_one_pass() -> None:
    for index in range(5):
        await add_event(payload={"index": index})
    sent, publish = collector()

    assert await run_relay(publish, batch_size=2) == 2
    assert len(sent) == 2


async def test_unreachable_broker_keeps_the_row_and_counts_the_attempt() -> None:
    """Критерий этапа: брокер недоступен — событие остаётся в базе."""
    message_id = await add_event()

    assert await run_relay(broken()) == 0

    row = await fetch(message_id)
    assert row.published_at is None
    assert row.attempts == 1
    assert row.last_error == "RuntimeError: broker is down"


async def test_attempts_grow_with_every_failure() -> None:
    message_id = await add_event()

    for _ in range(2):
        await run_relay(broken())

    assert (await fetch(message_id)).attempts == 2


async def test_recovered_broker_takes_everything_away() -> None:
    """Вторая половина критерия: брокер вернулся — строки уезжают."""
    message_id = await add_event()
    await run_relay(broken())
    sent, publish = collector()

    assert await run_relay(publish) == 1

    assert [event.message_id for event in sent] == [message_id]
    row = await fetch(message_id)
    assert row.published_at is not None
    # Счётчик попыток остаётся историей строки, а текст ошибки снимается:
    # заполненный `last_error` у опубликованной строки означает уход в DLQ.
    assert row.attempts == 1
    assert row.last_error is None


async def test_first_attempt_is_not_delayed() -> None:
    """Отсрочка касается повторов: свежее событие уезжает сразу."""
    await add_event()
    sent, publish = collector()

    assert await run_relay(publish, retry_base_delay=3600.0) == 1
    assert len(sent) == 1


async def test_failed_row_waits_out_its_backoff() -> None:
    now = datetime.now(tz=UTC)
    # Три неудачи при базовой отсрочке 5 секунд: строка снова видна релею,
    # когда её возраст перевалит за 5 * 2^2 = 20 секунд.
    await add_event(occurred_at=now - timedelta(seconds=5), attempts=3)
    sent, publish = collector()

    assert await run_relay(publish, retry_base_delay=5.0) == 0
    assert sent == []


async def test_overdue_row_is_picked_up_immediately() -> None:
    now = datetime.now(tz=UTC)
    await add_event(occurred_at=now - timedelta(seconds=25), attempts=3)
    sent, publish = collector()

    assert await run_relay(publish, retry_base_delay=5.0) == 1
    assert len(sent) == 1


async def test_backoff_never_exceeds_its_ceiling() -> None:
    """Без потолка 5 * 2^29 секунд означало бы «никогда»."""
    now = datetime.now(tz=UTC)
    await add_event(occurred_at=now - timedelta(seconds=30), attempts=30)
    sent, publish = collector()

    assert await run_relay(publish, retry_base_delay=5.0, retry_max_delay=10.0) == 1
    assert len(sent) == 1


async def test_batch_stops_at_the_first_failure() -> None:
    """Неудача публикации — это почти всегда транспорт, то есть все строки."""
    now = datetime.now(tz=UTC)
    first = await add_event(topic="a", occurred_at=now - timedelta(seconds=3))
    second = await add_event(topic="b", occurred_at=now - timedelta(seconds=2))
    third = await add_event(topic="c", occurred_at=now - timedelta(seconds=1))
    sent: list[OutgoingEvent] = []

    async def flaky(event: OutgoingEvent) -> None:
        if event.topic == "b":
            raise RuntimeError("broker is down")
        sent.append(event)

    assert await run_relay(flaky) == 1

    assert [event.message_id for event in sent] == [first]
    assert (await fetch(second)).attempts == 1
    # До третьей строки проход не дошёл: попытка ей не засчитана.
    assert (await fetch(third)).attempts == 0
    assert (await fetch(third)).published_at is None


async def test_exhausted_attempts_go_to_the_dead_letter() -> None:
    message_id = await add_event(topic="order.created")
    parked, dead_letter = collector()

    with capture_logs() as stream:
        assert await run_relay(broken(), dead_letter=dead_letter, max_attempts=1) == 0

    assert [event.message_id for event in parked] == [message_id]
    row = await fetch(message_id)
    # Строка закрыта, иначе релей перечитывал бы её вечно, но остаётся в
    # таблице с текстом ошибки — по нему разбирают инцидент.
    assert row.published_at is not None
    assert row.last_error == "RuntimeError: broker is down"
    assert row.attempts == 1

    logged = stream.getvalue()
    assert "outbox.dead_lettered" in logged
    assert "order.created" in logged
    assert str(message_id) in logged


async def test_row_survives_a_failed_dead_letter() -> None:
    """Иначе событие исчезло бы совсем: ни в брокере, ни в ожидающих."""
    message_id = await add_event()

    assert await run_relay(broken(), dead_letter=broken("dlx is down"), max_attempts=1) == 0

    row = await fetch(message_id)
    assert row.published_at is None
    assert row.attempts == 1


async def test_parallel_relays_never_publish_the_same_row() -> None:
    """Критерий этапа: два релея делят работу, а не дублируют её."""
    now = datetime.now(tz=UTC)
    for index in range(6):
        await add_event(payload={"index": index}, occurred_at=now - timedelta(seconds=6 - index))

    both_started = asyncio.Barrier(2)

    def publisher_of(sent: list[OutgoingEvent]) -> Publish:
        async def publish(event: OutgoingEvent) -> None:
            if not sent:
                # Первая публикация каждого релея ждёт соседа: без пересечения
                # во времени тест ничего бы не проверил. Соседний релей дойдёт
                # сюда только если не встал на блокировках первого.
                await asyncio.wait_for(both_started.wait(), 15)
            sent.append(event)

        return publish

    first: list[OutgoingEvent] = []
    second: list[OutgoingEvent] = []
    counts = await asyncio.gather(
        run_relay(publisher_of(first), batch_size=3),
        run_relay(publisher_of(second), batch_size=3),
    )

    assert list(counts) == [3, 3]
    delivered = [event.message_id for event in first + second]
    assert len(set(delivered)) == 6
    assert await count_rows() == 6


async def test_relay_does_not_block_writers() -> None:
    """Критерий этапа: релей держит строки, а не таблицу."""
    await add_event()
    locked = asyncio.Event()
    release = asyncio.Event()

    async def slow_publish(_event: OutgoingEvent) -> None:
        locked.set()
        await asyncio.wait_for(release.wait(), 15)

    relay = asyncio.create_task(run_relay(slow_publish))
    await asyncio.wait_for(locked.wait(), 15)

    # Пишущая транзакция идёт, пока релей держит блокировку своей строки.
    # Таймаут, а не измерение «на глаз»: блокировка таблицы повесила бы вставку
    # до конца прохода релея, то есть навсегда.
    written = await asyncio.wait_for(add_event(topic="tests.parallel"), 5)
    release.set()

    assert await asyncio.wait_for(relay, 15) == 1
    assert (await fetch(written)).published_at is None


async def test_purge_removes_only_old_published_rows() -> None:
    now = datetime.now(tz=UTC)
    stale = await add_event(published_at=now - timedelta(days=8))
    recent = await add_event(published_at=now - timedelta(days=1))
    waiting = await add_event()

    deleted = await purge_published_events(
        session_factory=session_module.session_factory,
        retention=timedelta(days=7),
    )

    assert deleted == 1
    assert await count_rows() == 2
    assert await fetch(recent) is not None
    assert await fetch(waiting) is not None
    async with session_module.session_factory() as db:
        assert await db.get(OutboxMessage, stale) is None


async def test_purge_keeps_dead_lettered_rows() -> None:
    """Единственный след инцидента расписание удалять не вправе."""
    now = datetime.now(tz=UTC)
    parked = await add_event(published_at=now - timedelta(days=30), last_error="RuntimeError: x")

    deleted = await purge_published_events(
        session_factory=session_module.session_factory,
        retention=timedelta(days=7),
    )

    assert deleted == 0
    assert (await fetch(parked)).last_error == "RuntimeError: x"
