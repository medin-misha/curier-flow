"""Тесты passive topology и строгого AMQP envelope."""

from typing import Any

import pytest
from aio_pika import ExchangeType

from conftest import MESSAGE_ID, FakeIncomingMessage
from telegram_bot.rabbitmq import (
    DEAD_LETTER_EXCHANGE,
    DEAD_LETTER_QUEUE,
    DOMAIN_EVENTS_EXCHANGE,
    PREFETCH_COUNT,
    QUEUE_NAME,
    RETRY_DELAY_MS,
    RETRY_EXCHANGE,
    RETRY_QUEUE,
    RETRY_RETURN_EXCHANGE,
    InvalidMessageError,
    _check_topology,
    validate_message,
)


class FakeEntity:
    """Именованная AMQP entity для passive-check assertions."""

    def __init__(self, name: str) -> None:
        self.name = name


class FakeTopologyChannel:
    """Записывающий channel без операций bind/declare topology."""

    def __init__(self) -> None:
        self.qos: list[dict[str, Any]] = []
        self.exchanges: list[tuple[str, ExchangeType, dict[str, Any]]] = []
        self.queues: list[tuple[str, dict[str, Any]]] = []

    async def set_qos(self, **kwargs: Any) -> None:
        """Записать qos."""
        self.qos.append(kwargs)

    async def declare_exchange(
        self,
        name: str,
        exchange_type: ExchangeType,
        **kwargs: Any,
    ) -> FakeEntity:
        """Записать passive exchange declaration."""
        self.exchanges.append((name, exchange_type, kwargs))
        return FakeEntity(name)

    async def declare_queue(self, name: str, **kwargs: Any) -> FakeEntity:
        """Записать passive queue declaration."""
        self.queues.append((name, kwargs))
        return FakeEntity(name)


async def test_topology_check_is_fully_passive_and_exact() -> None:
    """Bot не создаёт сущности и проверяет все durable/TTL/DLX параметры."""
    channel = FakeTopologyChannel()

    topology = await _check_topology(channel)  # type: ignore[arg-type]

    assert channel.qos == [{"prefetch_count": PREFETCH_COUNT}]
    assert channel.exchanges == [
        (DOMAIN_EVENTS_EXCHANGE, ExchangeType.TOPIC, {"durable": True, "passive": True}),
        (DEAD_LETTER_EXCHANGE, ExchangeType.FANOUT, {"durable": True, "passive": True}),
        (RETRY_RETURN_EXCHANGE, ExchangeType.FANOUT, {"durable": True, "passive": True}),
        (RETRY_EXCHANGE, ExchangeType.FANOUT, {"durable": True, "passive": True}),
    ]
    assert channel.queues == [
        (
            QUEUE_NAME,
            {
                "durable": True,
                "passive": True,
                "arguments": {"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE},
            },
        ),
        (DEAD_LETTER_QUEUE, {"durable": True, "passive": True}),
        (
            RETRY_QUEUE,
            {
                "durable": True,
                "passive": True,
                "arguments": {
                    "x-message-ttl": RETRY_DELAY_MS,
                    "x-dead-letter-exchange": RETRY_RETURN_EXCHANGE,
                },
            },
        ),
    ]
    assert topology.queue.name == QUEUE_NAME
    assert topology.retry_exchange.name == RETRY_EXCHANGE


def test_exact_envelope_is_validated() -> None:
    """Exact routing/content-type/message UUID и body принимаются."""
    validated = validate_message(FakeIncomingMessage())  # type: ignore[arg-type]

    assert validated.message_id == MESSAGE_ID
    assert validated.log_message_id == MESSAGE_ID
    assert validated.retry_attempt == 0
    assert validated.payload.platform == "wolt"


@pytest.mark.parametrize(
    "message",
    [
        FakeIncomingMessage(content_type="text/plain"),
        FakeIncomingMessage(routing_key="courier.registration.created"),
        FakeIncomingMessage(message_id=None),
        FakeIncomingMessage(message_id="not-a-uuid"),
        FakeIncomingMessage(body=b"not-json"),
        FakeIncomingMessage(headers={"x-retry-attempt": -1}),
        FakeIncomingMessage(headers={"x-retry-attempt": True}),
        FakeIncomingMessage(headers={"x-retry-attempt": "1"}),
    ],
)
def test_invalid_envelope_is_rejected(message: FakeIncomingMessage) -> None:
    """Нестрогий envelope не достигает Telegram client."""
    with pytest.raises(InvalidMessageError):
        validate_message(message)  # type: ignore[arg-type]


def test_retry_attempt_header_is_read() -> None:
    """Собственный retry counter сохраняет точное integer значение."""
    validated = validate_message(
        FakeIncomingMessage(headers={"x-retry-attempt": 3})  # type: ignore[arg-type]
    )

    assert validated.retry_attempt == 3
