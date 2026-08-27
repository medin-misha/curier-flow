"""RabbitMQ topology check, processing и delivery semantics."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import structlog
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
    ConsumerTag,
)
from aiormq.exceptions import ChannelNotFoundEntity, ChannelPreconditionFailed
from pydantic import ValidationError

from telegram_bot.contracts import CourierRegistrationNotification
from telegram_bot.rendering import render_notification
from telegram_bot.telegram import (
    TelegramAuthError,
    TelegramBotClient,
    TelegramError,
    TelegramNetworkError,
    TelegramPermanentError,
    TelegramRateLimitError,
    TelegramTransientError,
)

DOMAIN_EVENTS_EXCHANGE: Final = "domain.events"
ROUTING_KEY: Final = "courier.registration.telegram_notification.created"
QUEUE_NAME: Final = "telegram.notifications"
RETRY_EXCHANGE: Final = "telegram.notifications.retry"
RETRY_QUEUE: Final = "telegram.notifications.retry"
RETRY_RETURN_EXCHANGE: Final = "telegram.notifications.retry.return"
DEAD_LETTER_EXCHANGE: Final = "telegram.notifications.dlx"
DEAD_LETTER_QUEUE: Final = "telegram.notifications.dlq"
CONTENT_TYPE: Final = "application/json"
RETRY_ATTEMPT_HEADER: Final = "x-retry-attempt"
RETRY_DELAY_MS: Final = 30_000
PREFETCH_COUNT: Final = 1
TOPOLOGY_RETRY_INTERVAL: Final = 2.0

_logger = structlog.get_logger("telegram_bot.rabbitmq")

type Sleep = Callable[[float], Awaitable[None]]


class InvalidMessageError(Exception):
    """Нарушение payload или AMQP envelope контракта."""


class RetryPublishError(Exception):
    """Брокер не подтвердил retry copy."""


class TopologyConfigurationError(Exception):
    """Существующая topology не совпадает с зафиксированным контрактом."""


class StartupCancelledError(Exception):
    """Остановка запрошена во время ожидания topology."""


@dataclass(frozen=True, slots=True)
class PassiveTopology:
    """Пассивно полученные AMQP-сущности рабочего канала."""

    channel: AbstractChannel
    queue: AbstractQueue
    retry_exchange: AbstractExchange


@dataclass(frozen=True, slots=True)
class ValidatedMessage:
    """Проверенный payload и технические метаданные delivery."""

    payload: CourierRegistrationNotification
    message_id: str
    log_message_id: str
    retry_attempt: int


async def wait_for_topology(
    connection: AbstractRobustConnection,
    *,
    stop_event: asyncio.Event,
    retry_interval: float = TOPOLOGY_RETRY_INTERVAL,
) -> PassiveTopology:
    """Пассивно дождаться всех точных AMQP-сущностей backend."""
    while not stop_event.is_set():
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        try:
            topology = await _check_topology(channel)
        except ChannelNotFoundEntity:
            await _safe_close(channel)
            _logger.info(
                "telegram.topology_waiting",
                queue=QUEUE_NAME,
                error_class=ChannelNotFoundEntity.__name__,
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=retry_interval)
            except TimeoutError:
                continue
        except ChannelPreconditionFailed:
            await _safe_close(channel)
            raise TopologyConfigurationError from None
        else:
            return topology
    raise StartupCancelledError


async def _check_topology(channel: AbstractChannel) -> PassiveTopology:
    """Проверить existence/type/durability/arguments без создания topology."""
    await channel.set_qos(prefetch_count=PREFETCH_COUNT)

    await channel.declare_exchange(
        DOMAIN_EVENTS_EXCHANGE,
        ExchangeType.TOPIC,
        durable=True,
        passive=True,
    )
    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        passive=True,
        arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE},
    )
    await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE,
        ExchangeType.FANOUT,
        durable=True,
        passive=True,
    )
    await channel.declare_queue(
        DEAD_LETTER_QUEUE,
        durable=True,
        passive=True,
    )
    retry_return_exchange = await channel.declare_exchange(
        RETRY_RETURN_EXCHANGE,
        ExchangeType.FANOUT,
        durable=True,
        passive=True,
    )
    retry_exchange = await channel.declare_exchange(
        RETRY_EXCHANGE,
        ExchangeType.FANOUT,
        durable=True,
        passive=True,
    )
    await channel.declare_queue(
        RETRY_QUEUE,
        durable=True,
        passive=True,
        arguments={
            "x-message-ttl": RETRY_DELAY_MS,
            "x-dead-letter-exchange": RETRY_RETURN_EXCHANGE,
        },
    )
    # Переменная фиксирует, что return exchange действительно проверен до consume.
    del retry_return_exchange
    return PassiveTopology(channel=channel, queue=queue, retry_exchange=retry_exchange)


async def _safe_close(channel: AbstractChannel) -> None:
    """Закрыть ошибочный канал, не маскируя исходную startup-причину."""
    if channel.is_closed:
        return
    try:
        await channel.close()
    except Exception:
        return


class NotificationProcessor:
    """Применить ACK/retry/DLQ matrix к одному delivery."""

    def __init__(
        self,
        *,
        telegram: TelegramBotClient,
        retry_exchange: AbstractExchange,
        max_retries: int,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._telegram = telegram
        self._retry_exchange = retry_exchange
        self._max_retries = max_retries
        self._sleep = sleep

    async def process(self, message: AbstractIncomingMessage) -> None:
        """Отправить delivery и подтвердить только его окончательную судьбу."""
        started_at = time.monotonic()
        try:
            validated = validate_message(message)
        except InvalidMessageError:
            await message.reject(requeue=False)
            _logger.warning(
                "telegram.notification_dead_lettered",
                message_id=_safe_log_message_id(message.message_id),
                topic=ROUTING_KEY,
                attempt=_safe_retry_attempt(message.headers),
                error_class=InvalidMessageError.__name__,
                duration_ms=_duration_ms(started_at),
            )
            return

        text = render_notification(validated.payload)
        try:
            await self._telegram.send_message(
                telegram_id=validated.payload.telegram_id,
                text=text,
            )
        except TelegramAuthError:
            raise
        except TelegramPermanentError as error:
            await message.reject(requeue=False)
            _logger.warning(
                "telegram.notification_dead_lettered",
                message_id=validated.log_message_id,
                topic=ROUTING_KEY,
                attempt=validated.retry_attempt,
                telegram_status=error.status_code,
                error_class=type(error).__name__,
                duration_ms=_duration_ms(started_at),
            )
            return
        except TelegramRateLimitError as error:
            await self._retry_or_dead_letter(
                message,
                validated=validated,
                error=error,
                started_at=started_at,
                retry_after=error.retry_after,
            )
            return
        except (TelegramNetworkError, TelegramTransientError) as error:
            await self._retry_or_dead_letter(
                message,
                validated=validated,
                error=error,
                started_at=started_at,
            )
            return

        await message.ack()
        _logger.info(
            "telegram.notification_sent",
            message_id=validated.log_message_id,
            topic=ROUTING_KEY,
            attempt=validated.retry_attempt,
            duration_ms=_duration_ms(started_at),
        )

    async def _retry_or_dead_letter(
        self,
        message: AbstractIncomingMessage,
        *,
        validated: ValidatedMessage,
        error: TelegramError,
        started_at: float,
        retry_after: int = 0,
    ) -> None:
        """Подтверждённо опубликовать retry либо завершить лимит в DLQ."""
        if validated.retry_attempt >= self._max_retries:
            await message.reject(requeue=False)
            _logger.warning(
                "telegram.notification_dead_lettered",
                message_id=validated.log_message_id,
                topic=ROUTING_KEY,
                attempt=validated.retry_attempt,
                telegram_status=error.status_code,
                error_class="RetryLimitExceeded",
                duration_ms=_duration_ms(started_at),
            )
            return

        remaining_delay = max(0.0, float(retry_after) - RETRY_DELAY_MS / 1000)
        if remaining_delay:
            await self._sleep(remaining_delay)

        try:
            await self._retry_exchange.publish(
                _retry_message(message, retry_attempt=validated.retry_attempt + 1),
                routing_key=message.routing_key or ROUTING_KEY,
                mandatory=True,
            )
        except Exception:
            # Исключение драйвера может содержать repr AMQP message с PII.
            raise RetryPublishError from None

        # Publisher confirm обязательно завершился до ACK исходного delivery.
        await message.ack()
        _logger.info(
            "telegram.notification_retrying",
            message_id=validated.log_message_id,
            topic=ROUTING_KEY,
            attempt=validated.retry_attempt + 1,
            delay_ms=RETRY_DELAY_MS + int(remaining_delay * 1000),
            telegram_status=error.status_code,
            error_class=type(error).__name__,
            duration_ms=_duration_ms(started_at),
        )


class NotificationConsumer:
    """Один prefetch=1 consumer с graceful in-flight drain."""

    def __init__(
        self,
        *,
        connection: AbstractRobustConnection,
        telegram: TelegramBotClient,
        max_retries: int,
        stop_event: asyncio.Event,
    ) -> None:
        self._connection = connection
        self._telegram = telegram
        self._max_retries = max_retries
        self._stop_event = stop_event
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._consumer_tag: ConsumerTag | None = None
        self._processor: NotificationProcessor | None = None
        self._in_flight: set[asyncio.Task[Any]] = set()
        self._idle = asyncio.Event()
        self._idle.set()
        self._stopped = False
        self.fatal_event = asyncio.Event()
        self.fatal_error: Exception | None = None

    async def start(self) -> None:
        """Пассивно проверить topology и подписаться с prefetch=1."""
        topology = await wait_for_topology(self._connection, stop_event=self._stop_event)
        self._channel = topology.channel
        self._queue = topology.queue
        self._processor = NotificationProcessor(
            telegram=self._telegram,
            retry_exchange=topology.retry_exchange,
            max_retries=self._max_retries,
        )
        self._consumer_tag = await topology.queue.consume(self._on_message, no_ack=False)
        _logger.info(
            "telegram.consumer_started",
            queue=QUEUE_NAME,
            topic=ROUTING_KEY,
            prefetch=PREFETCH_COUNT,
        )

    async def stop(self, *, drain_timeout: float) -> None:
        """Отменить consume, ограниченно дождаться in-flight и закрыть channel."""
        if self._stopped:
            return
        self._stopped = True

        if self._queue is not None and self._consumer_tag is not None:
            await self._queue.cancel(self._consumer_tag)

        try:
            await asyncio.wait_for(self._idle.wait(), timeout=drain_timeout)
        except TimeoutError:
            _logger.warning(
                "telegram.shutdown_timed_out",
                in_flight=len(self._in_flight),
                timeout=drain_timeout,
            )
            for task in tuple(self._in_flight):
                task.cancel()
            if self._in_flight:
                await asyncio.gather(*self._in_flight, return_exceptions=True)

        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """Учесть callback как in-flight и остановить процесс на fatal error."""
        task = asyncio.current_task()
        if task is not None:
            self._in_flight.add(task)
        self._idle.clear()
        try:
            if self._processor is None:
                raise RuntimeError("consumer is not started")
            await self._processor.process(message)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._mark_fatal(message, error)
        finally:
            if task is not None:
                self._in_flight.discard(task)
            if not self._in_flight:
                self._idle.set()

    def _mark_fatal(self, message: AbstractIncomingMessage, error: Exception) -> None:
        """Сигнализировать worker без ACK/NACK текущего delivery."""
        if self.fatal_error is None:
            self.fatal_error = error
            self.fatal_event.set()
        event = (
            "telegram.authentication_failed"
            if isinstance(error, TelegramAuthError)
            else "telegram.consumer_failed"
        )
        _logger.error(
            event,
            message_id=_safe_log_message_id(message.message_id),
            topic=ROUTING_KEY,
            attempt=_safe_retry_attempt(message.headers),
            telegram_status=getattr(error, "status_code", None),
            error_class=type(error).__name__,
        )


def validate_message(message: AbstractIncomingMessage) -> ValidatedMessage:
    """Проверить exact envelope, JSON schema, UUID и retry header."""
    if message.content_type != CONTENT_TYPE or message.routing_key != ROUTING_KEY:
        raise InvalidMessageError

    message_id = message.message_id
    if not isinstance(message_id, str) or not message_id:
        raise InvalidMessageError
    try:
        parsed_message_id = UUID(message_id)
    except (TypeError, ValueError, AttributeError):
        raise InvalidMessageError from None

    retry_attempt = _retry_attempt(message.headers)
    try:
        payload = CourierRegistrationNotification.model_validate_json(message.body)
    except (ValidationError, ValueError, TypeError):
        raise InvalidMessageError from None

    return ValidatedMessage(
        payload=payload,
        message_id=message_id,
        log_message_id=str(parsed_message_id),
        retry_attempt=retry_attempt,
    )


def _retry_attempt(headers: Mapping[str, Any] | None) -> int:
    """Строго прочитать собственный неотрицательный retry counter."""
    if not headers or RETRY_ATTEMPT_HEADER not in headers:
        return 0
    attempt = headers[RETRY_ATTEMPT_HEADER]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
        raise InvalidMessageError
    return attempt


def _safe_retry_attempt(headers: Mapping[str, Any] | None) -> int | None:
    """Вернуть безопасный attempt для terminal-лога malformed delivery."""
    try:
        return _retry_attempt(headers)
    except InvalidMessageError:
        return None


def _safe_log_message_id(message_id: str | None) -> str | None:
    """Не логировать произвольное значение вместо разрешённого UUID."""
    if not message_id:
        return None
    try:
        return str(UUID(message_id))
    except (TypeError, ValueError, AttributeError):
        return None


def _retry_message(message: AbstractIncomingMessage, *, retry_attempt: int) -> Message:
    """Скопировать контрактные свойства и увеличить retry counter."""
    headers = dict(message.headers or {})
    headers[RETRY_ATTEMPT_HEADER] = retry_attempt
    return Message(
        body=message.body,
        headers=headers,
        content_type=message.content_type,
        content_encoding=message.content_encoding,
        delivery_mode=DeliveryMode.PERSISTENT,
        priority=message.priority,
        correlation_id=message.correlation_id,
        reply_to=message.reply_to,
        message_id=message.message_id,
        timestamp=message.timestamp,
        type=message.type,
        app_id=message.app_id,
    )


def _duration_ms(started_at: float) -> int:
    """Округлить техническую длительность обработки до миллисекунд."""
    return max(0, round((time.monotonic() - started_at) * 1000))
