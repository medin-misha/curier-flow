"""Admin fan-out: courier.registered → durable Telegram notification events."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import partial
from typing import Any
from uuid import UUID, uuid4

import pytest
from aio_pika import DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db import session as session_module
from app.kernel.events.bus import subscribe
from app.kernel.events.models import OutboxMessage, ProcessedMessage
from app.kernel.events.outbox import DOMAIN_EVENTS_TOPOLOGY, OutboxSettings, relay_outbox
from app.kernel.events.registry import EventRegistry, build_event_registry
from app.kernel.registry import ConsumerDecl, Module, TopologyDecl
from app.modules.admin.events import CourierRegistered, DeliveryPlatform
from app.modules.admin.models import Admin, AdminRefreshToken
from app.modules.admin.module import TELEGRAM_NOTIFICATIONS_TOPOLOGY, admin_module
from app.modules.admin.schemas.requests import AdminPatch
from app.modules.admin.services import fan_out_courier_registration_notifications, patch_admin
from app.modules.admin.subscribers import handle_courier_registered
from app.platform.domain_events import CONTENT_TYPE, deliver_to_subscribers, publisher
from app.platform.rabbitmq import (
    ConsumerGroup,
    declare_topology,
    derived_names,
    open_channel,
    publish,
)
from tests.amqp import message_count, unique, wait_for_message, wait_until_delivered

pytestmark = pytest.mark.usefixtures("admin_notifications_database")

NOTIFICATION_TOPIC = "courier.registration.telegram_notification.created"


@pytest.fixture
async def admin_notifications_database(clean_db: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Изолировать admin-строки, которых нет в общей clean_db fixture."""

    async def clear_admins() -> None:
        async with session_module.session_factory() as session, session.begin():
            await session.execute(delete(AdminRefreshToken))
            await session.execute(delete(Admin))

    await clear_admins()
    yield
    await clear_admins()


async def seed_admin(*, telegram_id: int | None, is_active: bool = True) -> Admin:
    """Создать Admin без дорогой auth-подготовки, ненужной fan-out тестам."""
    async with session_module.session_factory() as session, session.begin():
        admin = Admin(
            username=f"admin-{uuid4().hex[:8]}",
            hashed_password="not-used-by-notification-tests",  # noqa: S106
            telegram_id=telegram_id,
            is_active=is_active,
        )
        session.add(admin)
        await session.flush()
    return admin


def courier_registered(
    *,
    platforms: list[DeliveryPlatform] | None = None,
    contact_platform: str | None = None,
    contact: str | None = None,
) -> CourierRegistered:
    """Собрать валидную локальную проекцию courier.registered."""
    return CourierRegistered(
        courier_id=uuid4(),
        full_name="Jan Novak",
        contact_platform=contact_platform,
        contact=contact,
        platforms=platforms or [DeliveryPlatform.WOLT],
    )


def isolated_topologies() -> tuple[TopologyDecl, TopologyDecl]:
    """Собрать внутреннюю и Telegram topology на одном уникальном exchange."""
    exchange = unique("tests.admin.domain.events")
    internal = replace(
        DOMAIN_EVENTS_TOPOLOGY,
        exchange=exchange,
        queue=unique("tests.admin.domain.subscribers"),
    )
    telegram = replace(
        TELEGRAM_NOTIFICATIONS_TOPOLOGY,
        exchange=exchange,
        queue=unique("tests.telegram.notifications"),
    )
    return internal, telegram


async def declare(
    broker: AbstractRobustConnection,
    *topology: TopologyDecl,
) -> None:
    """Объявить тестовую topology через production adapter."""
    async with open_channel(broker) as channel:
        await declare_topology(channel, topology)


async def publish_registration(
    broker: AbstractRobustConnection,
    topology: TopologyDecl,
    event: CourierRegistered,
    *,
    message_id: UUID,
) -> None:
    """Положить courier.registered с управляемым AMQP message_id."""
    async with open_channel(broker) as channel:
        await publish(
            channel,
            exchange=topology.exchange,
            routing_key=event.topic,
            body=event.model_dump_json().encode(),
            message_id=str(message_id),
            content_type=CONTENT_TYPE,
        )


@asynccontextmanager
async def subscribers_running(
    broker: AbstractRobustConnection,
    topology: TopologyDecl,
    registry: EventRegistry,
) -> AsyncIterator[None]:
    """Запустить production ConsumerGroup для внутреннего event subscriber."""
    async with open_channel(broker) as channel:
        consumer = ConsumerDecl(
            queue=topology.queue,
            handler=partial(
                deliver_to_subscribers,
                registry,
                channel,
                derived_names(topology.queue).dead_letter_exchange,
            ),
        )
        group = ConsumerGroup(
            broker,
            [consumer],
            [topology],
            session_factory=session_module.session_factory,
            max_retries=0,
        )
        await group.start()
        try:
            yield
        finally:
            await group.stop(15)


async def notification_payloads() -> list[dict[str, Any]]:
    """Вернуть готовые Telegram payload из outbox."""
    async with session_module.session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(OutboxMessage.payload)
                    .where(OutboxMessage.topic == NOTIFICATION_TOPIC)
                    .order_by(OutboxMessage.occurred_at, OutboxMessage.id)
                )
            ).all()
        )


async def processed_count() -> int:
    """Посчитать transaction marks обработанных сообщений."""
    async with session_module.session_factory() as session:
        return await session.scalar(select(func.count()).select_from(ProcessedMessage)) or 0


async def relay_notifications(
    broker: AbstractRobustConnection,
    internal: TopologyDecl,
) -> int:
    """Опубликовать notification outbox через production relay/publisher."""
    async with open_channel(broker) as channel:
        return await relay_outbox(
            session_factory=session_module.session_factory,
            publish=publisher(channel, internal.exchange),
            dead_letter=publisher(
                channel,
                derived_names(internal.queue).dead_letter_exchange,
            ),
            settings=OutboxSettings(retry_base_delay=0.0),
        )


async def test_fan_out_publishes_exact_persistent_admin_by_platform_messages(
    broker: AbstractRobustConnection,
) -> None:
    """Только active linked Admin получают ровно admins × platforms сообщений."""
    await seed_admin(telegram_id=1001)
    await seed_admin(telegram_id=1002)
    await seed_admin(telegram_id=2001, is_active=False)
    await seed_admin(telegram_id=None)
    event = courier_registered(
        platforms=[
            DeliveryPlatform.WOLT,
            DeliveryPlatform.FOODORA,
            DeliveryPlatform.BOLT_FOOD,
        ]
    )
    internal, telegram = isolated_topologies()
    await declare(broker, internal, telegram)

    await publish_registration(broker, internal, event, message_id=uuid4())
    registry = build_event_registry([admin_module])
    async with subscribers_running(broker, internal, registry):
        await wait_until_delivered(broker, internal.queue)

    assert await relay_notifications(broker, internal) == 6
    messages = [await wait_for_message(broker, telegram.queue) for _ in range(6)]
    assert await message_count(broker, telegram.queue) == 0
    assert all(message.delivery_mode == DeliveryMode.PERSISTENT for message in messages)
    assert all(message.content_type == CONTENT_TYPE for message in messages)

    payloads = [json.loads(message.body) for message in messages]
    expected = [
        {
            "telegram_id": telegram_id,
            "full_name": "Jan Novak",
            "contact_platform": None,
            "contact": None,
            "platform": platform.value,
        }
        for telegram_id in (1001, 1002)
        for platform in (
            DeliveryPlatform.WOLT,
            DeliveryPlatform.FOODORA,
            DeliveryPlatform.BOLT_FOOD,
        )
    ]

    def notification_key(payload: dict[str, Any]) -> tuple[int, str]:
        return payload["telegram_id"], payload["platform"]

    assert sorted(payloads, key=notification_key) == sorted(expected, key=notification_key)
    assert all(set(payload) == set(expected[0]) for payload in payloads)


async def test_no_recipients_is_a_successful_noop() -> None:
    """Пустой recipient snapshot не создаёт notification outbox rows."""
    await seed_admin(telegram_id=1001, is_active=False)
    await seed_admin(telegram_id=None)

    async with session_module.session_factory() as session, session.begin():
        await fan_out_courier_registration_notifications(
            courier_registered(),
            session=session,
        )

    assert await notification_payloads() == []


async def test_replayed_message_id_does_not_repeat_fan_out(
    broker: AbstractRobustConnection,
) -> None:
    """processed_messages делает повтор того же AMQP message_id безвредным."""
    await seed_admin(telegram_id=1001)
    event = courier_registered()
    message_id = uuid4()
    internal, _telegram = isolated_topologies()
    await declare(broker, internal)
    registry = build_event_registry([admin_module])

    for _ in range(2):
        await publish_registration(broker, internal, event, message_id=message_id)
        async with subscribers_running(broker, internal, registry):
            await wait_until_delivered(broker, internal.queue)

    assert len(await notification_payloads()) == 1
    assert await processed_count() == 1


async def test_failing_subscriber_rolls_back_mark_and_all_notification_rows(
    broker: AbstractRobustConnection,
) -> None:
    """Сбой общей subscriber transaction откатывает fan-out и message mark."""
    await seed_admin(telegram_id=1001)
    await seed_admin(telegram_id=1002)
    event = courier_registered(platforms=[DeliveryPlatform.WOLT, DeliveryPlatform.FOODORA])

    @subscribe(CourierRegistered)
    async def fail_after_fan_out(
        _event: CourierRegistered,
        _session: AsyncSession,
    ) -> None:
        raise RuntimeError("subscriber refused the transaction")

    registry = build_event_registry(
        [
            Module(
                name="admin-rollback-test",
                subscribers=(handle_courier_registered, fail_after_fan_out),
            )
        ]
    )
    internal, _telegram = isolated_topologies()
    await declare(broker, internal)
    await publish_registration(broker, internal, event, message_id=uuid4())

    async with subscribers_running(broker, internal, registry):
        await wait_for_message(
            broker,
            derived_names(internal.queue).dead_letter_queue,
        )

    assert await notification_payloads() == []
    assert await processed_count() == 0


async def test_telegram_id_is_snapshotted_before_a_later_patch() -> None:
    """Готовый payload не следует за последующим изменением Admin.telegram_id."""
    admin = await seed_admin(telegram_id=1001)
    async with session_module.session_factory() as session, session.begin():
        await handle_courier_registered(courier_registered(), session)

    async with session_module.session_factory() as session, session.begin():
        await patch_admin(
            admin.id,
            AdminPatch(telegram_id=2002),
            session=session,
        )

    payloads = await notification_payloads()
    assert len(payloads) == 1
    assert payloads[0]["telegram_id"] == 1001


def test_admin_manifest_declares_exact_telegram_topology_without_consumer() -> None:
    """Subscriber и sending-only queue подключены только декларациями манифеста."""
    assert admin_module.subscribers == (handle_courier_registered,)
    assert admin_module.topology == (TELEGRAM_NOTIFICATIONS_TOPOLOGY,)
    assert admin_module.consumers == ()
    assert (
        TopologyDecl(
            exchange="domain.events",
            queue="telegram.notifications",
            routing_key=NOTIFICATION_TOPIC,
            exchange_type="topic",
            durable=True,
            dead_letter=True,
            retry_ttl_ms=30_000,
        )
        == TELEGRAM_NOTIFICATIONS_TOPOLOGY
    )

    names = derived_names(TELEGRAM_NOTIFICATIONS_TOPOLOGY.queue)
    assert names.retry_exchange == "telegram.notifications.retry"
    assert names.retry_queue == "telegram.notifications.retry"
    assert names.retry_return_exchange == "telegram.notifications.retry.return"
    assert names.dead_letter_exchange == "telegram.notifications.dlx"
    assert names.dead_letter_queue == "telegram.notifications.dlq"


async def test_telegram_queue_retry_and_dlq_exist_before_first_publication(
    broker: AbstractRobustConnection,
) -> None:
    """Worker startup может создать всю durable topology при выключенном bot."""
    await declare(broker, TELEGRAM_NOTIFICATIONS_TOPOLOGY)
    names = derived_names(TELEGRAM_NOTIFICATIONS_TOPOLOGY.queue)

    async with open_channel(broker) as channel:
        for exchange in (
            TELEGRAM_NOTIFICATIONS_TOPOLOGY.exchange,
            names.retry_exchange,
            names.retry_return_exchange,
            names.dead_letter_exchange,
        ):
            await channel.declare_exchange(exchange, passive=True)
        for queue in (
            TELEGRAM_NOTIFICATIONS_TOPOLOGY.queue,
            names.retry_queue,
            names.dead_letter_queue,
        ):
            await channel.declare_queue(queue, passive=True)
