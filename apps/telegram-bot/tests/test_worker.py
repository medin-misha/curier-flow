"""Тесты ACK/retry/DLQ matrix и lifecycle worker."""

import asyncio
import json
from typing import Any

import pytest
from aio_pika import DeliveryMode, Message
from pydantic import SecretStr
from structlog.testing import capture_logs

from conftest import MESSAGE_ID, VALID_PAYLOAD, FakeIncomingMessage
from telegram_bot.config import Settings
from telegram_bot.rabbitmq import (
    CONTENT_TYPE,
    RETRY_ATTEMPT_HEADER,
    ROUTING_KEY,
    NotificationConsumer,
    NotificationProcessor,
    RetryPublishError,
)
from telegram_bot.telegram import (
    TelegramAuthError,
    TelegramBotClient,
    TelegramNetworkError,
    TelegramPermanentError,
    TelegramRateLimitError,
    TelegramTransientError,
)
from telegram_bot.worker import run_service


class FakeTelegram:
    """Telegram client с заданным исходом sendMessage."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.error = error
        self.events = [] if events is None else events
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, *, telegram_id: int, text: str) -> None:
        """Записать вызов и вернуть настроенную ошибку."""
        self.events.append("send")
        self.calls.append({"telegram_id": telegram_id, "text": text})
        if self.error is not None:
            raise self.error


class FakeRetryExchange:
    """Publisher с наблюдаемым моментом broker confirm."""

    def __init__(
        self,
        *,
        events: list[str] | None = None,
        confirmation: bool = True,
        error: Exception | None = None,
    ) -> None:
        self.events = [] if events is None else events
        self.confirmation = confirmation
        self.error = error
        self.published: list[tuple[Message, str, bool]] = []

    async def publish(
        self,
        message: Message,
        *,
        routing_key: str,
        mandatory: bool,
    ) -> bool:
        """Имитировать подтверждённую либо неуспешную публикацию."""
        self.events.append("publish")
        self.published.append((message, routing_key, mandatory))
        if self.error is not None:
            raise self.error
        if not self.confirmation:
            raise RetryPublishError
        self.events.append("publish_confirmed")
        return self.confirmation


def processor(
    telegram: FakeTelegram,
    exchange: FakeRetryExchange,
    *,
    max_retries: int = 5,
    sleep: Any = asyncio.sleep,
) -> NotificationProcessor:
    """Построить processor на test doubles."""
    return NotificationProcessor(
        telegram=telegram,  # type: ignore[arg-type]
        retry_exchange=exchange,  # type: ignore[arg-type]
        max_retries=max_retries,
        sleep=sleep,
    )


async def test_success_sends_once_and_then_acks() -> None:
    """Успешный side effect предшествует единственному ACK."""
    events: list[str] = []
    telegram = FakeTelegram(events=events)
    message = FakeIncomingMessage(events=events)

    await processor(telegram, FakeRetryExchange(events=events)).process(message)  # type: ignore[arg-type]

    assert events == ["send", "ack"]
    assert len(telegram.calls) == 1
    assert telegram.calls[0]["telegram_id"] == VALID_PAYLOAD["telegram_id"]
    assert message.acked is True
    assert message.rejected is False


@pytest.mark.parametrize(
    "message",
    [
        FakeIncomingMessage(body=b"not-json"),
        FakeIncomingMessage(payload={**VALID_PAYLOAD, "extra": "forbidden"}),
        FakeIncomingMessage(content_type="text/plain"),
        FakeIncomingMessage(message_id=None),
        FakeIncomingMessage(message_id="invalid"),
    ],
)
async def test_invalid_message_goes_directly_to_dlq(message: FakeIncomingMessage) -> None:
    """Invalid delivery отклоняется без Bot API и retry publish."""
    telegram = FakeTelegram()
    exchange = FakeRetryExchange()

    await processor(telegram, exchange).process(message)  # type: ignore[arg-type]

    assert telegram.calls == []
    assert exchange.published == []
    assert message.rejected is True
    assert message.requeue is False
    assert message.acked is False


@pytest.mark.parametrize("status", [400, 403, 404])
async def test_permanent_4xx_goes_directly_to_dlq(status: int) -> None:
    """Chat-related и прочие permanent 4xx не образуют retry loop."""
    telegram = FakeTelegram(error=TelegramPermanentError(status_code=status))
    exchange = FakeRetryExchange()
    message = FakeIncomingMessage()

    await processor(telegram, exchange).process(message)  # type: ignore[arg-type]

    assert message.rejected is True
    assert message.requeue is False
    assert message.acked is False
    assert exchange.published == []


@pytest.mark.parametrize(
    "error",
    [
        TelegramNetworkError(),
        TelegramTransientError(status_code=500),
        TelegramTransientError(status_code=503),
    ],
)
async def test_transient_error_publishes_retry_with_preserved_metadata(
    error: Exception,
) -> None:
    """Network/5xx сохраняют body, routing, UUID, headers и correlation."""
    events: list[str] = []
    telegram = FakeTelegram(error=error, events=events)
    exchange = FakeRetryExchange(events=events)
    message = FakeIncomingMessage(
        headers={"request_id": "request-1", "traceparent": "trace-1"},
        events=events,
    )

    await processor(telegram, exchange).process(message)  # type: ignore[arg-type]

    assert events == ["send", "publish", "publish_confirmed", "ack"]
    retry, routing_key, mandatory = exchange.published[0]
    assert retry.body == message.body
    assert retry.message_id == MESSAGE_ID
    assert retry.content_type == CONTENT_TYPE
    assert retry.correlation_id == "correlation-id"
    assert retry.headers == {
        "request_id": "request-1",
        "traceparent": "trace-1",
        RETRY_ATTEMPT_HEADER: 1,
    }
    assert retry.delivery_mode == DeliveryMode.PERSISTENT
    assert routing_key == ROUTING_KEY
    assert mandatory is True
    assert message.acked is True


async def test_retry_publisher_confirm_is_required_before_ack() -> None:
    """Broker NACK retry copy оставляет исходное delivery unacked."""
    telegram = FakeTelegram(error=TelegramNetworkError())
    exchange = FakeRetryExchange(confirmation=False)
    message = FakeIncomingMessage()

    with pytest.raises(RetryPublishError):
        await processor(telegram, exchange).process(message)  # type: ignore[arg-type]

    assert len(exchange.published) == 1
    assert message.acked is False
    assert message.rejected is False


async def test_retry_publish_exception_leaves_original_unacked() -> None:
    """Ошибка publisher не ACK'ает и не теряет исходное delivery."""
    telegram = FakeTelegram(error=TelegramNetworkError())
    exchange = FakeRetryExchange(error=ConnectionError("broker unavailable"))
    message = FakeIncomingMessage()

    with pytest.raises(RetryPublishError):
        await processor(telegram, exchange).process(message)  # type: ignore[arg-type]

    assert message.acked is False
    assert message.rejected is False


async def test_retry_limit_dead_letters_without_another_publish() -> None:
    """Попытка на configured limit завершается в DLQ."""
    telegram = FakeTelegram(error=TelegramTransientError(status_code=500))
    exchange = FakeRetryExchange()
    message = FakeIncomingMessage(headers={RETRY_ATTEMPT_HEADER: 5})

    await processor(telegram, exchange, max_retries=5).process(message)  # type: ignore[arg-type]

    assert message.rejected is True
    assert message.requeue is False
    assert exchange.published == []


async def test_429_waits_only_retry_after_remainder() -> None:
    """Общая пауза retry queue плюс async wait не короче retry_after."""
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    telegram = FakeTelegram(error=TelegramRateLimitError(retry_after=45))
    exchange = FakeRetryExchange()
    message = FakeIncomingMessage()

    await processor(telegram, exchange, sleep=sleep).process(message)  # type: ignore[arg-type]

    assert delays == [15.0]
    assert exchange.published[0][0].headers[RETRY_ATTEMPT_HEADER] == 1
    assert message.acked is True


async def test_429_with_short_retry_after_uses_queue_ttl_only() -> None:
    """retry_after короче 30 секунд не добавляет лишнюю локальную задержку."""
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    telegram = FakeTelegram(error=TelegramRateLimitError(retry_after=10))
    message = FakeIncomingMessage()

    await processor(telegram, FakeRetryExchange(), sleep=sleep).process(message)  # type: ignore[arg-type]

    assert delays == []
    assert message.acked is True


async def test_401_is_fatal_and_leaves_message_unacked() -> None:
    """Runtime token error не превращается ни в retry, ни в DLQ."""
    telegram = FakeTelegram(error=TelegramAuthError(status_code=401))
    message = FakeIncomingMessage()

    with pytest.raises(TelegramAuthError):
        await processor(telegram, FakeRetryExchange()).process(message)  # type: ignore[arg-type]

    assert message.acked is False
    assert message.rejected is False


async def test_no_pii_or_arbitrary_message_id_in_structured_logs() -> None:
    """Логи не содержат Courier PII, rendered text или malformed message ID."""
    sensitive_values = [
        "987654321",
        "Sensitive Courier",
        "@private-contact",
        "signal-private",
        "sensitive-not-a-uuid",
    ]
    sensitive_payload = {
        **VALID_PAYLOAD,
        "telegram_id": 987654321,
        "full_name": "Sensitive Courier",
        "contact_platform": "signal-private",
        "contact": "@private-contact",
    }
    valid_message = FakeIncomingMessage(payload=sensitive_payload)
    invalid_message = FakeIncomingMessage(
        body=json.dumps({**sensitive_payload, "extra": "private"}).encode(),
        message_id="sensitive-not-a-uuid",
    )

    with capture_logs() as logs:
        await processor(FakeTelegram(), FakeRetryExchange()).process(valid_message)  # type: ignore[arg-type]
        await processor(FakeTelegram(), FakeRetryExchange()).process(invalid_message)  # type: ignore[arg-type]

    serialized = json.dumps(logs, ensure_ascii=False, default=str)
    for value in sensitive_values:
        assert value not in serialized
    assert MESSAGE_ID in serialized
    assert "telegram.notification_sent" in serialized
    assert "telegram.notification_dead_lettered" in serialized


async def test_stub_api_success_is_acked(telegram_stub: Any) -> None:
    """Processor integration использует loopback stub, а не Telegram network."""
    telegram_stub.enqueue(200, {"ok": True, "result": {"message_id": 1}})
    client = TelegramBotClient(
        token=SecretStr("stub-token"),
        timeout=1,
        base_url=telegram_stub.base_url,
    )
    message = FakeIncomingMessage()

    async with client:
        await NotificationProcessor(
            telegram=client,
            retry_exchange=FakeRetryExchange(),  # type: ignore[arg-type]
            max_retries=5,
        ).process(message)  # type: ignore[arg-type]

    assert message.acked is True
    assert telegram_stub.requests[0].path == "/botstub-token/sendMessage"


async def test_redelivery_after_send_succeeds_but_ack_connection_fails() -> None:
    """Падение в окне side effect → ACK допускает повторную отправку."""
    telegram = FakeTelegram()
    first = FakeIncomingMessage(ack_error=ConnectionError("connection lost"))

    with pytest.raises(ConnectionError):
        await processor(telegram, FakeRetryExchange()).process(first)  # type: ignore[arg-type]

    redelivered = FakeIncomingMessage()
    await processor(telegram, FakeRetryExchange()).process(redelivered)  # type: ignore[arg-type]

    assert len(telegram.calls) == 2
    assert first.acked is False
    assert redelivered.acked is True


class FakeChannel:
    """Channel с наблюдаемым close для shutdown tests."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.is_closed = False

    async def close(self) -> None:
        """Закрыть channel."""
        self.events.append("channel_close")
        self.is_closed = True


class FakeQueue:
    """Queue с наблюдаемой отменой consume."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def cancel(self, consumer_tag: str) -> None:
        """Отменить subscription."""
        assert consumer_tag == "consumer-tag"
        self.events.append("cancel_consume")


class BlockingProcessor:
    """Processor, который позволяет контролировать in-flight момент."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def process(self, message: FakeIncomingMessage) -> None:
        """Ждать release и затем ACK."""
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        await message.ack()


def prepared_consumer(
    *,
    events: list[str],
    test_processor: Any,
) -> NotificationConsumer:
    """Построить уже подписанный consumer для isolated shutdown test."""
    consumer = NotificationConsumer(
        connection=object(),  # type: ignore[arg-type]
        telegram=FakeTelegram(),  # type: ignore[arg-type]
        max_retries=5,
        stop_event=asyncio.Event(),
    )
    consumer._channel = FakeChannel(events)  # type: ignore[assignment]
    consumer._queue = FakeQueue(events)  # type: ignore[assignment]
    consumer._consumer_tag = "consumer-tag"
    consumer._processor = test_processor
    return consumer


async def test_shutdown_cancels_consume_and_drains_in_flight() -> None:
    """SIGTERM path перестаёт брать новое до ожидания активного delivery."""
    events: list[str] = []
    blocking = BlockingProcessor()
    consumer = prepared_consumer(events=events, test_processor=blocking)
    message = FakeIncomingMessage(events=events)
    delivery_task = asyncio.create_task(consumer._on_message(message))  # type: ignore[arg-type]
    await blocking.started.wait()

    stop_task = asyncio.create_task(consumer.stop(drain_timeout=1))
    await asyncio.sleep(0)
    assert events == ["cancel_consume"]

    blocking.release.set()
    await delivery_task
    await stop_task

    assert events == ["cancel_consume", "ack", "channel_close"]
    assert message.acked is True


async def test_shutdown_timeout_cancels_in_flight_for_redelivery() -> None:
    """После timeout channel закрывается, а unacked delivery вернётся в queue."""
    events: list[str] = []
    blocking = BlockingProcessor()
    consumer = prepared_consumer(events=events, test_processor=blocking)
    message = FakeIncomingMessage(events=events)
    delivery_task = asyncio.create_task(consumer._on_message(message))  # type: ignore[arg-type]
    await blocking.started.wait()

    with capture_logs() as logs:
        await consumer.stop(drain_timeout=0.001)
    await asyncio.gather(delivery_task, return_exceptions=True)

    assert blocking.cancelled is True
    assert message.acked is False
    assert message.rejected is False
    assert events == ["cancel_consume", "channel_close"]
    assert any(record["event"] == "telegram.shutdown_timed_out" for record in logs)


class RaisingProcessor:
    """Processor, который имитирует runtime 401."""

    async def process(self, message: FakeIncomingMessage) -> None:
        """Оставить message unacked через auth error."""
        del message
        raise TelegramAuthError(status_code=401)


async def test_consumer_marks_401_fatal_without_settling_delivery() -> None:
    """Fatal event будит worker, который закроет channel и завершится."""
    consumer = prepared_consumer(events=[], test_processor=RaisingProcessor())
    message = FakeIncomingMessage()

    await consumer._on_message(message)  # type: ignore[arg-type]

    assert consumer.fatal_event.is_set()
    assert isinstance(consumer.fatal_error, TelegramAuthError)
    assert message.acked is False
    assert message.rejected is False


class LifecycleTelegram:
    """Контекстный fake для startup order."""

    def __init__(self, events: list[str], error: Exception | None = None) -> None:
        self.events = events
        self.error = error

    async def __aenter__(self) -> "LifecycleTelegram":
        """Открыть fake client."""
        self.events.append("http_open")
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Закрыть fake client."""
        self.events.append("http_close")

    async def get_me(self) -> None:
        """Записать token check."""
        self.events.append("get_me")
        if self.error is not None:
            raise self.error


class LifecycleConnection:
    """Robust connection fake для lifecycle order."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def close(self) -> None:
        """Закрыть connection."""
        self.events.append("rabbit_close")


class LifecycleConsumer:
    """Consumer fake, который инициирует graceful stop после старта."""

    def __init__(self, events: list[str], stop_event: asyncio.Event) -> None:
        self.events = events
        self.stop_event = stop_event
        self.fatal_event = asyncio.Event()
        self.fatal_error = None

    async def start(self) -> None:
        """Имитировать начало consume и входящий SIGTERM."""
        self.events.append("consume")
        self.stop_event.set()

    async def stop(self, *, drain_timeout: float) -> None:
        """Имитировать graceful consumer stop."""
        assert drain_timeout == 30
        self.events.append("consumer_stop")


def settings() -> Settings:
    """Настройки lifecycle tests без .env."""
    return Settings(_env_file=None, telegram_bot_token="stub-token")


async def test_get_me_happens_before_rabbitmq_consume() -> None:
    """Startup проверяет token до connection и consume."""
    events: list[str] = []
    stop_event = asyncio.Event()
    telegram = LifecycleTelegram(events)

    async def open_rabbit(_settings: Settings) -> Any:
        events.append("rabbit_open")
        return LifecycleConnection(events)

    def make_consumer(
        _connection: Any,
        _telegram: Any,
        _settings: Settings,
        consumer_stop_event: asyncio.Event,
    ) -> Any:
        return LifecycleConsumer(events, consumer_stop_event)

    await run_service(
        settings(),
        stop_event=stop_event,
        connection_opener=open_rabbit,
        telegram_factory=lambda _settings: telegram,  # type: ignore[arg-type]
        consumer_factory=make_consumer,  # type: ignore[arg-type]
    )

    assert events == [
        "http_open",
        "get_me",
        "rabbit_open",
        "consume",
        "consumer_stop",
        "rabbit_close",
        "http_close",
    ]


async def test_startup_401_never_connects_or_consumes() -> None:
    """Auth failure getMe роняет startup, не затрагивая queued messages."""
    events: list[str] = []
    stop_event = asyncio.Event()
    telegram = LifecycleTelegram(events, TelegramAuthError(status_code=401))

    async def forbidden_connection(_settings: Settings) -> Any:
        events.append("unexpected_rabbit")
        return LifecycleConnection(events)

    with pytest.raises(TelegramAuthError):
        await run_service(
            settings(),
            stop_event=stop_event,
            connection_opener=forbidden_connection,
            telegram_factory=lambda _settings: telegram,  # type: ignore[arg-type]
        )

    assert events == ["http_open", "get_me", "http_close"]
