"""Транспорт RabbitMQ: топология, идемпотентность, повторы, DLQ, остановка.

Тесты идут против настоящего брокера в контейнере: почти всё, что здесь
проверяется, — это поведение самого RabbitMQ (dead-lettering, x-message-ttl,
возврат unacked-сообщений при закрытии канала). Мок вернул бы то, что мы в
него заложили, и молчал бы ровно про те случаи, ради которых написан код.
"""

import asyncio
import json
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pika
import pytest
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from aiormq.exceptions import ChannelNotFoundEntity
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context import request_id
from app.kernel.db import session as session_module
from app.kernel.events.models import ProcessedMessage
from app.kernel.registry import ConsumerDecl, TopologyDecl
from app.platform.rabbitmq import (
    RETRY_ATTEMPT_HEADER,
    ConsumerConfigError,
    ConsumerGroup,
    declare_topology,
    derived_names,
    message_key,
    open_channel,
    publish,
)
from tests.amqp import message_count, unique, wait_for_message, wait_until_delivered
from tests.models import Widget


def _fake_message(message_id: str | None) -> AbstractIncomingMessage:
    """Сообщение, у которого важен только идентификатор."""
    return Mock(spec=AbstractIncomingMessage, message_id=message_id)


def publish_without_id(dsn: str, exchange: str, routing_key: str) -> None:
    """Публикация синхронным клиентом, не подставляющим message_id."""
    conn = pika.BlockingConnection(pika.URLParameters(dsn))
    try:
        conn.channel().basic_publish(
            exchange,
            routing_key,
            b"{}",
            pika.BasicProperties(delivery_mode=2),
        )
    finally:
        conn.close()


async def count_rows(model: type[Widget] | type[ProcessedMessage]) -> int:
    async with session_module.session_factory() as db:
        result = await db.execute(select(func.count()).select_from(model))
        return result.scalar_one()


def test_derived_names_are_built_from_the_queue() -> None:
    names = derived_names("orders.sync")

    assert names.dead_letter_exchange == "orders.sync.dlx"
    assert names.dead_letter_queue == "orders.sync.dlq"
    assert names.retry_exchange == "orders.sync.retry"
    assert names.retry_queue == "orders.sync.retry"
    assert names.retry_return_exchange == "orders.sync.retry.return"


async def test_declaration_creates_every_derived_entity(broker: AbstractRobustConnection) -> None:
    queue = unique("tests.topology")
    decl = TopologyDecl(
        exchange=unique("tests.exchange"),
        queue=queue,
        routing_key="thing.*",
        retry_ttl_ms=500,
    )
    names = derived_names(queue)

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])

    # passive-объявление не создаёт сущность, а падает, если её нет.
    async with open_channel(broker) as channel:
        for exchange in (
            decl.exchange,
            names.dead_letter_exchange,
            names.retry_exchange,
            names.retry_return_exchange,
        ):
            await channel.declare_exchange(exchange, passive=True)
        for name in (queue, names.dead_letter_queue, names.retry_queue):
            await channel.declare_queue(name, passive=True)


async def test_declaration_is_idempotent(broker: AbstractRobustConnection) -> None:
    """Перезапуск процесса не должен спотыкаться о собственную топологию."""
    decl = TopologyDecl(
        exchange=unique("tests.exchange"),
        queue=unique("tests.repeat"),
        routing_key="thing.done",
        retry_ttl_ms=100,
    )

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await declare_topology(channel, [decl])


async def test_duplicate_delivery_is_handled_once(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """Критерий этапа: публикация → потребление → повтор того же message_id."""
    queue = unique("tests.orders")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="widget.created")
    handled: list[str] = []

    async def handler(message: AbstractIncomingMessage, db: AsyncSession) -> None:
        payload = json.loads(message.body)
        handled.append(payload["name"])
        db.add(Widget(name=payload["name"]))

    message_id = str(uuid4())
    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        for _ in range(2):
            await publish(
                channel,
                exchange=decl.exchange,
                routing_key="widget.created",
                body=json.dumps({"name": "bolt"}).encode(),
                message_id=message_id,
            )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await wait_until_delivered(broker, queue)
    await group.stop(10)

    assert handled == ["bolt"]
    assert await count_rows(Widget) == 1
    assert await count_rows(ProcessedMessage) == 1


async def test_consumer_without_idempotency_handles_every_delivery(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    queue = unique("tests.metrics")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="ping")
    handled: list[str] = []

    async def handler(message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        handled.append(message.body.decode())

    message_id = str(uuid4())
    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        for _ in range(2):
            await publish(
                channel,
                exchange=decl.exchange,
                routing_key="ping",
                body=b"tick",
                message_id=message_id,
            )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler, requires_idempotency=False)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await wait_until_delivered(broker, queue)
    await group.stop(10)

    assert handled == ["tick", "tick"]
    assert await count_rows(ProcessedMessage) == 0


async def test_foreign_message_id_is_still_deduplicated(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """У чужого сервиса свой формат идентификаторов, а гарантия нужна та же."""
    queue = unique("tests.partner")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="invoice")
    handled: list[str] = []

    async def handler(message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        handled.append(message.message_id or "")

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        for _ in range(2):
            await publish(
                channel,
                exchange=decl.exchange,
                routing_key="invoice",
                body=b"{}",
                message_id="INV-2024-0001",
            )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await wait_until_delivered(broker, queue)
    await group.stop(10)

    assert handled == ["INV-2024-0001"]
    assert await count_rows(ProcessedMessage) == 1


def test_message_key_is_stable_and_distinct() -> None:
    assert message_key(_fake_message("INV-1")) == message_key(_fake_message("INV-1"))
    assert message_key(_fake_message("INV-1")) != message_key(_fake_message("INV-2"))
    assert message_key(_fake_message(None)) is None
    known = uuid4()
    assert message_key(_fake_message(str(known))) == known


async def test_message_without_any_id_is_parked_not_processed(
    broker: AbstractRobustConnection,
    rabbitmq_dsn: str,
    clean_db: None,  # noqa: ARG001
) -> None:
    """Дедупликацию обещали, а дедуплицировать не по чему: повтор не поможет."""
    queue = unique("tests.anonymous")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="anon")
    handled: list[bytes] = []

    async def handler(message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        handled.append(message.body)

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
    # Через aio-pika такое сообщение не отправить: aiormq подставляет
    # собственный message_id, если публикующий его не задал. Чужой сервис на
    # другом клиенте может прислать сообщение вообще без него.
    await asyncio.to_thread(publish_without_id, rabbitmq_dsn, decl.exchange, "anon")

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=3,
    )
    await group.start()
    parked = await wait_for_message(broker, derived_names(queue).dead_letter_queue)
    await group.stop(10)

    assert parked.body == b"{}"
    assert handled == []


async def test_failed_handler_retries_then_dead_letters(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    queue = unique("tests.flaky")
    decl = TopologyDecl(
        exchange=unique("tests.events"),
        queue=queue,
        routing_key="thing.done",
        retry_ttl_ms=200,
    )
    attempts: list[Any] = []

    async def handler(message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        attempts.append(message.headers.get(RETRY_ATTEMPT_HEADER, 0))
        raise RuntimeError("handler is broken")

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="thing.done",
            body=b"{}",
            message_id=str(uuid4()),
        )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=1,
    )
    await group.start()
    parked = await wait_for_message(broker, derived_names(queue).dead_letter_queue)
    await group.stop(10)

    assert attempts == [0, 1]
    assert parked.headers[RETRY_ATTEMPT_HEADER] == 1
    # Упавшая попытка не оставляет отметки: иначе повтор счёлся бы дубликатом.
    assert await count_rows(ProcessedMessage) == 0


async def test_retry_preserves_the_routing_key(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """Возврат через свой обмен, а не через x-dead-letter-routing-key."""
    queue = unique("tests.routed")
    decl = TopologyDecl(
        exchange=unique("tests.events"),
        queue=queue,
        routing_key="order.#",
        retry_ttl_ms=200,
    )
    seen: list[str] = []

    async def handler(message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        seen.append(message.routing_key or "")
        raise RuntimeError("handler is broken")

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="order.created",
            body=b"{}",
            message_id=str(uuid4()),
        )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=1,
    )
    await group.start()
    await wait_for_message(broker, derived_names(queue).dead_letter_queue)
    await group.stop(10)

    assert seen == ["order.created", "order.created"]


async def test_stop_waits_for_the_message_in_flight(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """SIGTERM посреди обработки: работа доводится до конца, сообщение снимается."""
    queue = unique("tests.slow")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="slow.job")
    started = asyncio.Event()
    finished = asyncio.Event()

    async def handler(_message: AbstractIncomingMessage, db: AsyncSession) -> None:
        started.set()
        await asyncio.sleep(0.5)
        db.add(Widget(name="slow"))
        finished.set()

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="slow.job",
            body=b"{}",
            message_id=str(uuid4()),
        )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await asyncio.wait_for(started.wait(), 10)
    await group.stop(10)

    assert finished.is_set()
    assert await count_rows(Widget) == 1
    # Канал закрыт: неподтверждённое сообщение брокер вернул бы в очередь.
    assert await message_count(broker, queue) == 0


async def test_stop_returns_unfinished_work_to_the_queue(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """Обработчик не уложился в таймаут: сообщение возвращается, а не пропадает."""
    queue = unique("tests.stubborn")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="stubborn")
    started = asyncio.Event()
    released = asyncio.Event()

    async def handler(_message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        started.set()
        await released.wait()

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="stubborn",
            body=b"{}",
            message_id=str(uuid4()),
        )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await asyncio.wait_for(started.wait(), 10)
    await group.stop(0.1)
    released.set()

    assert await message_count(broker, queue) == 1


async def test_failure_without_dead_letter_drops_the_message(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """Выключенный dead_letter — это и есть согласие потерять сообщение."""
    queue = unique("tests.disposable")
    decl = TopologyDecl(
        exchange=unique("tests.events"),
        queue=queue,
        routing_key="disposable",
        dead_letter=False,
    )
    seen = asyncio.Event()

    async def handler(_message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        seen.set()
        raise RuntimeError("handler is broken")

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="disposable",
            body=b"{}",
            message_id=str(uuid4()),
        )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await asyncio.wait_for(seen.wait(), 10)
    await wait_until_delivered(broker, queue)
    await group.stop(10)

    async with open_channel(broker) as channel:
        with pytest.raises(ChannelNotFoundEntity):
            await channel.declare_queue(derived_names(queue).dead_letter_queue, passive=True)


async def test_request_id_is_restored_from_the_message(
    broker: AbstractRobustConnection,
    clean_db: None,  # noqa: ARG001
) -> None:
    """Логи обработчика должны связываться с логами того, кто прислал сообщение."""
    queue = unique("tests.traced")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="traced")
    seen: list[str] = []

    async def handler(_message: AbstractIncomingMessage, _db: AsyncSession) -> None:
        seen.append(request_id.get())

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="traced",
            body=b"{}",
            message_id=str(uuid4()),
            headers={"request_id": "req-42"},
        )
        await publish(
            channel,
            exchange=decl.exchange,
            routing_key="traced",
            body=b"{}",
            message_id=str(uuid4()),
        )

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler, prefetch=1)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await wait_until_delivered(broker, queue)
    await group.stop(10)

    assert seen[0] == "req-42"
    # Второе сообщение без заголовка: подставляется его message_id.
    assert seen[1] != "-"
    assert request_id.get() == "-"


async def test_stop_is_idempotent(broker: AbstractRobustConnection) -> None:
    """Остановку зовут и по сигналу, и при разматывании стека выхода."""
    queue = unique("tests.quiet")
    decl = TopologyDecl(exchange=unique("tests.events"), queue=queue, routing_key="quiet")

    async def handler(_message: AbstractIncomingMessage, _db: AsyncSession) -> None: ...

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue=queue, handler=handler)],
        [decl],
        session_factory=session_module.session_factory,
        max_retries=0,
    )
    await group.start()
    await group.stop(5)
    await group.stop(5)


async def test_consumer_without_topology_fails_on_start(
    broker: AbstractRobustConnection,
) -> None:
    async def handler(_message: AbstractIncomingMessage, _db: AsyncSession) -> None: ...

    group = ConsumerGroup(
        broker,
        [ConsumerDecl(queue="tests.never-declared", handler=handler)],
        [],
        session_factory=session_module.session_factory,
        max_retries=0,
    )

    with pytest.raises(ConsumerConfigError, match=r"tests\.never-declared"):
        await group.start()


async def test_publish_to_a_dead_end_is_reported(broker: AbstractRobustConnection) -> None:
    """mandatory=True: сообщение, которому некуда лечь, не теряется молча."""
    decl = TopologyDecl(
        exchange=unique("tests.events"),
        queue=unique("tests.bound"),
        routing_key="known.key",
    )

    async with open_channel(broker) as channel:
        await declare_topology(channel, [decl])
        with pytest.raises(Exception, match=r"NO_ROUTE|Message"):
            await publish(
                channel,
                exchange=decl.exchange,
                routing_key="unknown.key",
                body=b"{}",
                message_id=str(uuid4()),
            )
