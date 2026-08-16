"""Доменное событие целиком: от коммита сервиса до вызова подписчика.

Путь собран на настоящей инфраструктуре и из настоящих кусков — `emit()`,
релей, обмен RabbitMQ, `ConsumerGroup`, `run_once`, реестр подписчиков. Мок в
середине этой цепочки проверял бы только то, что мы в него заложили, а
интересны ровно стыки: доедет ли `message_id` до `processed_messages`, вернётся
ли сообщение в очередь при падении подписчика, что случится с топиком, которого
никто не ждёт.

Топология в каждом тесте своя (`isolated_topology`): брокер в контейнере один
на прогон, и сообщения, оставшиеся от соседнего теста, приезжали бы не туда.
Форма при этом та же, что у системной топологии, — тесты проверяют её же
настройки, а не свои.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import partial
from io import StringIO
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from aio_pika.abc import AbstractRobustConnection
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context import actor_id, request_id
from app.kernel.db import session as session_module
from app.kernel.db.session import get_uow
from app.kernel.events.bus import DomainEvent, emit, subscribe
from app.kernel.events.models import OutboxMessage, ProcessedMessage
from app.kernel.events.outbox import (
    DOMAIN_EVENTS_TOPOLOGY,
    OutboxSettings,
    relay_outbox,
)
from app.kernel.events.registry import EventRegistry, Subscriber, build_event_registry
from app.kernel.registry import ConsumerDecl, Module, TopologyDecl
from app.platform.domain_events import deliver_to_subscribers, publisher
from app.platform.rabbitmq import (
    ConsumerGroup,
    declare_topology,
    derived_names,
    open_channel,
    publish,
)
from app.worker import build_system_module
from tests.amqp import message_count, unique, wait_for_message, wait_until_delivered
from tests.logs import capture_logs
from tests.models import Widget

pytestmark = pytest.mark.usefixtures("clean_db")

uow = asynccontextmanager(get_uow)


class WidgetOrdered(DomainEvent):
    """Событие, на которое в тестах кто-то подписан."""

    topic: ClassVar[str] = "tests.widget.ordered"

    name: str


class WidgetForgotten(DomainEvent):
    """Событие, класса которого нет в реестре потребителя."""

    topic: ClassVar[str] = "tests.widget.forgotten"

    name: str


def isolated_topology() -> TopologyDecl:
    """Системная топология доменных событий с уникальными именами."""
    return replace(
        DOMAIN_EVENTS_TOPOLOGY,
        exchange=unique("tests.domain.events"),
        queue=unique("tests.domain.subscribers"),
    )


def registry_of(*subscribers: Subscriber) -> EventRegistry:
    """Реестр из одного тестового модуля."""
    return build_event_registry([Module(name="tests", subscribers=subscribers)])


async def relay(
    conn: AbstractRobustConnection,
    topology: TopologyDecl,
    **overrides: Any,
) -> int:
    """Один проход релея с настоящей публикацией в брокер."""
    async with open_channel(conn) as channel:
        return await relay_outbox(
            session_factory=session_module.session_factory,
            publish=publisher(channel, topology.exchange),
            dead_letter=publisher(channel, derived_names(topology.queue).dead_letter_exchange),
            settings=OutboxSettings(**{"retry_base_delay": 0.0, **overrides}),
        )


@asynccontextmanager
async def subscribers_running(
    conn: AbstractRobustConnection,
    topology: TopologyDecl,
    registry: EventRegistry,
    *,
    max_retries: int = 0,
) -> AsyncIterator[None]:
    """Поднять консьюмер доменных событий на время блока.

    Выход из блока останавливает группу, то есть дожидается сообщений в
    работе: проверять эффекты подписчиков раньше этого момента бессмысленно —
    очередь пустеет в момент выдачи сообщения, а не его обработки.
    """
    async with open_channel(conn) as channel:
        decl = ConsumerDecl(
            queue=topology.queue,
            handler=partial(
                deliver_to_subscribers,
                registry,
                channel,
                derived_names(topology.queue).dead_letter_exchange,
            ),
        )
        group = ConsumerGroup(
            conn,
            [decl],
            [topology],
            session_factory=session_module.session_factory,
            max_retries=max_retries,
        )
        await group.start()
        try:
            yield
        finally:
            await group.stop(15)


async def declare(conn: AbstractRobustConnection, topology: TopologyDecl) -> None:
    async with open_channel(conn) as channel:
        await declare_topology(channel, [topology])


def only_record(stream: StringIO, event: str) -> dict[str, Any]:
    """Единственная запись лога с этим именем события.

    В буфер попадают логи всего процесса, включая SQLAlchemy и aio-pika,
    поэтому нужную запись приходится отбирать по имени, а не читать первую.
    """
    records: list[dict[str, Any]] = [json.loads(line) for line in stream.getvalue().splitlines()]
    found = [record for record in records if record.get("event") == event]
    assert len(found) == 1, f"expected exactly one {event} record, got {len(found)}"
    return found[0]


async def count_rows(model: type[Widget] | type[ProcessedMessage]) -> int:
    async with session_module.session_factory() as db:
        result = await db.execute(select(func.count()).select_from(model))
        return result.scalar_one()


async def unpublish_everything() -> None:
    """Вернуть outbox в состояние «ещё не опубликовано».

    Так воспроизводится повторная публикация того же `message_id`: релей,
    упавший между публикацией и коммитом, при следующем проходе отправит
    сообщение второй раз, и потребитель обязан это пережить.
    """
    async with session_module.session_factory() as db, db.begin():
        await db.execute(update(OutboxMessage).values(published_at=None))


async def test_service_call_reaches_the_subscriber_exactly_once(
    broker: AbstractRobustConnection,
) -> None:
    """Критерий этапа: сервис вызван — подписчик отработал ровно один раз."""
    handled: list[str] = []

    @subscribe(WidgetOrdered)
    async def remember(event: WidgetOrdered, session: AsyncSession) -> None:
        handled.append(event.name)
        session.add(Widget(name=event.name))

    topology = isolated_topology()
    await declare(broker, topology)

    async with uow() as session:
        emit(session, WidgetOrdered(name="bolt"))

    assert await relay(broker, topology) == 1

    async with subscribers_running(broker, topology, registry_of(remember)):
        await wait_until_delivered(broker, topology.queue)

    assert handled == ["bolt"]
    assert await count_rows(Widget) == 1
    assert await count_rows(ProcessedMessage) == 1


async def test_second_delivery_of_the_same_row_changes_nothing(
    broker: AbstractRobustConnection,
) -> None:
    """Доставка at-least-once: повтор обязан быть безвредным."""
    handled: list[str] = []

    @subscribe(WidgetOrdered)
    async def remember(event: WidgetOrdered, session: AsyncSession) -> None:
        handled.append(event.name)
        session.add(Widget(name=event.name))

    topology = isolated_topology()
    registry = registry_of(remember)
    await declare(broker, topology)

    async with uow() as session:
        emit(session, WidgetOrdered(name="bolt"))

    for _ in range(2):
        await relay(broker, topology)
        async with subscribers_running(broker, topology, registry):
            await wait_until_delivered(broker, topology.queue)
        await unpublish_everything()

    assert handled == ["bolt"]
    assert await count_rows(Widget) == 1
    assert await count_rows(ProcessedMessage) == 1


async def test_broker_outage_holds_events_until_it_is_over(
    broker: AbstractRobustConnection,
) -> None:
    """Критерий этапа: брокер недоступен — событие ждёт, потом уезжает."""
    handled: list[str] = []

    @subscribe(WidgetOrdered)
    async def remember(event: WidgetOrdered, _session: AsyncSession) -> None:
        handled.append(event.name)

    topology = isolated_topology()
    await declare(broker, topology)

    async with uow() as session:
        emit(session, WidgetOrdered(name="bolt"))

    async def unavailable(_event: object) -> None:
        raise ConnectionError("broker is down")

    published = await relay_outbox(
        session_factory=session_module.session_factory,
        publish=unavailable,
        dead_letter=unavailable,
        settings=OutboxSettings(retry_base_delay=0.0),
    )
    assert published == 0

    async with session_module.session_factory() as db:
        waiting = (await db.scalars(select(OutboxMessage))).one()
    assert waiting.published_at is None
    assert waiting.attempts == 1

    # Брокер вернулся: настоящая публикация, настоящая доставка.
    assert await relay(broker, topology) == 1
    async with subscribers_running(broker, topology, registry_of(remember)):
        await wait_until_delivered(broker, topology.queue)

    assert handled == ["bolt"]


async def test_subscribers_see_the_context_of_the_original_request(
    broker: AbstractRobustConnection,
) -> None:
    """Иначе логи подписчика не связать с запросом, который его породил."""
    seen: list[tuple[str, UUID | None]] = []
    actor = uuid4()

    @subscribe(WidgetOrdered)
    async def remember(_event: WidgetOrdered, _session: AsyncSession) -> None:
        seen.append((request_id.get(), actor_id.get()))

    topology = isolated_topology()
    await declare(broker, topology)

    request_token = request_id.set("req-99")
    actor_token = actor_id.set(actor)
    try:
        async with uow() as session:
            emit(session, WidgetOrdered(name="bolt"))
    finally:
        actor_id.reset(actor_token)
        request_id.reset(request_token)

    await relay(broker, topology)
    async with subscribers_running(broker, topology, registry_of(remember)):
        await wait_until_delivered(broker, topology.queue)

    assert seen == [("req-99", actor)]
    # Контекст сообщения не должен пережить его обработку.
    assert request_id.get() == "-"
    assert actor_id.get() is None


async def test_failing_subscriber_rolls_back_its_neighbours(
    broker: AbstractRobustConnection,
) -> None:
    """Подписчики одного сообщения делят транзакцию: либо все, либо никто."""
    ran: list[str] = []

    @subscribe(WidgetOrdered)
    async def first(event: WidgetOrdered, session: AsyncSession) -> None:
        ran.append("first")
        session.add(Widget(name=event.name))

    @subscribe(WidgetOrdered)
    async def second(_event: WidgetOrdered, _session: AsyncSession) -> None:
        ran.append("second")
        raise RuntimeError("subscriber is broken")

    topology = isolated_topology()
    await declare(broker, topology)

    async with uow() as session:
        emit(session, WidgetOrdered(name="bolt"))
    await relay(broker, topology)

    async with subscribers_running(broker, topology, registry_of(first, second)):
        parked = await wait_for_message(broker, derived_names(topology.queue).dead_letter_queue)

    assert ran == ["first", "second"]
    assert parked.body != b""
    # Ни данных первого подписчика, ни отметки об обработке: повтор обязан
    # застать сообщение необработанным.
    assert await count_rows(Widget) == 0
    assert await count_rows(ProcessedMessage) == 0


async def test_event_without_subscribers_is_acknowledged_without_dead_lettering(
    broker: AbstractRobustConnection,
) -> None:
    """Событие, которое некому обработать, — штатная ситуация, а не авария.

    Очередь связана по `#`, поэтому в неё приезжают все события сервиса, в том
    числе те, на которые никто не подписан (в шаблоне такое есть:
    `FileConfirmed`). Копия каждого такого события в DLQ и запись уровня error
    превратили бы обычную работу сервиса в поток ложных тревог.
    """
    handled: list[str] = []

    @subscribe(WidgetOrdered)
    async def remember(event: WidgetOrdered, _session: AsyncSession) -> None:
        handled.append(event.name)

    topology = isolated_topology()
    await declare(broker, topology)

    async with uow() as session:
        emit(session, WidgetForgotten(name="ghost"))
        emit(session, WidgetOrdered(name="bolt"))

    assert await relay(broker, topology) == 2

    with capture_logs() as stream:
        async with subscribers_running(broker, topology, registry_of(remember)):
            await wait_until_delivered(broker, topology.queue)

    # Соседнее сообщение обработано: консьюмер пережил событие без подписчиков.
    assert handled == ["bolt"]
    assert await message_count(broker, derived_names(topology.queue).dead_letter_queue) == 0

    record = only_record(stream, "domain_events.no_subscribers")
    assert record["level"] == "warning"
    assert record["topic"] == "tests.widget.forgotten"


async def test_payload_that_does_not_match_the_schema_is_parked(
    broker: AbstractRobustConnection,
) -> None:
    """Повтор такого сообщения ничего не исправит, значит и повторять нечего.

    В отличие от события без подписчиков, здесь сообщение испорчено, и тело
    обязано сохраниться в DLQ: без него разбирать инцидент не по чему.
    """
    handled: list[str] = []

    @subscribe(WidgetOrdered)
    async def remember(event: WidgetOrdered, _session: AsyncSession) -> None:
        handled.append(event.name)

    topology = isolated_topology()
    await declare(broker, topology)

    async with open_channel(broker) as channel:
        await publish(
            channel,
            exchange=topology.exchange,
            routing_key=WidgetOrdered.topic,
            body=b'{"quantity": 3}',
            message_id=str(uuid4()),
        )

    with capture_logs() as stream:
        async with subscribers_running(broker, topology, registry_of(remember)):
            parked = await wait_for_message(broker, derived_names(topology.queue).dead_letter_queue)

    assert parked.body == b'{"quantity": 3}'
    assert handled == []

    record = only_record(stream, "domain_events.invalid_payload")
    assert record["level"] == "error"
    assert record["topic"] == WidgetOrdered.topic


async def test_system_tasks_work_on_the_real_wiring(
    broker: AbstractRobustConnection,
) -> None:
    """Задачи воркера — единственное место, где сходятся канал, база и настройки.

    Топология здесь системная, а не уникальная: проверяется именно та проводка,
    которая уедет в прод, включая имена обмена и очереди.
    """
    async with uow() as session:
        emit(session, WidgetOrdered(name="bolt"))

    async with open_channel(broker) as channel:
        await declare_topology(channel, [DOMAIN_EVENTS_TOPOLOGY])
        # Все системные задачи вызываются без аргументов: канал, фабрику сессий
        # и настройки сборка зашила в замыкания. Прогоняются все, а не только
        # релей: так проверка не разъедется с составом манифеста.
        for task in build_system_module(channel, registry_of()).tasks:
            await task()

    async with session_module.session_factory() as db:
        row = (await db.scalars(select(OutboxMessage))).one()
    assert row.published_at is not None
    assert row.attempts == 0


async def test_unreadable_actor_does_not_stop_delivery(
    broker: AbstractRobustConnection,
) -> None:
    """Заголовок нужен логам: испорченный — повод пожать плечами, а не упасть."""
    seen: list[UUID | None] = []

    @subscribe(WidgetOrdered)
    async def remember(_event: WidgetOrdered, _session: AsyncSession) -> None:
        seen.append(actor_id.get())

    topology = isolated_topology()
    await declare(broker, topology)

    async with open_channel(broker) as channel:
        await publish(
            channel,
            exchange=topology.exchange,
            routing_key=WidgetOrdered.topic,
            body=b'{"name": "bolt"}',
            message_id=str(uuid4()),
            headers={"actor_id": "not-a-uuid"},
        )

    async with subscribers_running(broker, topology, registry_of(remember)):
        await wait_until_delivered(broker, topology.queue)

    assert seen == [None]


async def test_two_relays_deliver_each_event_once(
    broker: AbstractRobustConnection,
) -> None:
    """Тот же `SKIP LOCKED`, но на всём пути: подписчик не должен видеть дублей."""
    handled: list[str] = []

    @subscribe(WidgetOrdered)
    async def remember(event: WidgetOrdered, session: AsyncSession) -> None:
        handled.append(event.name)
        session.add(Widget(name=event.name))

    topology = isolated_topology()
    await declare(broker, topology)

    async with uow() as session:
        for index in range(6):
            emit(session, WidgetOrdered(name=f"bolt-{index}"))

    counts = await asyncio.gather(
        relay(broker, topology, batch_size=3),
        relay(broker, topology, batch_size=3),
    )
    assert sum(counts) == 6

    async with subscribers_running(broker, topology, registry_of(remember)):
        await wait_until_delivered(broker, topology.queue)

    assert sorted(handled) == [f"bolt-{index}" for index in range(6)]
    assert await count_rows(Widget) == 6
