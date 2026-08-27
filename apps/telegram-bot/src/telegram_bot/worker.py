"""Process entrypoint и graceful lifecycle sending-only worker."""

import asyncio
import signal
import sys
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import structlog
from aio_pika import connect_robust
from aio_pika.abc import AbstractRobustConnection

from telegram_bot.config import Settings
from telegram_bot.logging import configure_logging
from telegram_bot.rabbitmq import NotificationConsumer, StartupCancelledError
from telegram_bot.telegram import TelegramBotClient

_logger = structlog.get_logger("telegram_bot.worker")

ConnectionOpener = Callable[
    [Settings],
    Coroutine[Any, Any, AbstractRobustConnection],
]
TelegramFactory = Callable[[Settings], TelegramBotClient]
ConsumerFactory = Callable[
    [AbstractRobustConnection, TelegramBotClient, Settings, asyncio.Event],
    NotificationConsumer,
]


async def open_connection(settings: Settings) -> AbstractRobustConnection:
    """Открыть robust connection с диагностируемым именем процесса."""
    return await connect_robust(
        _robust_dsn(str(settings.rabbitmq_dsn)),
        client_properties={"connection_name": settings.app_name},
    )


def _robust_dsn(dsn: str) -> str:
    """Добавить startup reconnect без логирования RabbitMQ credentials."""
    parts = urlsplit(dsn)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["fail_fast"] = "0"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_telegram(settings: Settings) -> TelegramBotClient:
    """Построить Bot API client из скрытого SecretStr."""
    return TelegramBotClient(
        token=settings.telegram_bot_token,
        timeout=settings.telegram_api_timeout,
    )


def build_consumer(
    connection: AbstractRobustConnection,
    telegram: TelegramBotClient,
    settings: Settings,
    stop_event: asyncio.Event,
) -> NotificationConsumer:
    """Построить AMQP consumer с настройками retry и shutdown."""
    return NotificationConsumer(
        connection=connection,
        telegram=telegram,
        max_retries=settings.telegram_max_retries,
        stop_event=stop_event,
    )


async def run_service(
    settings: Settings,
    *,
    stop_event: asyncio.Event,
    connection_opener: ConnectionOpener = open_connection,
    telegram_factory: TelegramFactory = build_telegram,
    consumer_factory: ConsumerFactory = build_consumer,
) -> None:
    """Проверить getMe, начать consume и корректно закрыть ресурсы."""
    telegram = telegram_factory(settings)
    async with telegram:
        # RabbitMQ и consume намеренно начинаются только после успешного getMe.
        await telegram.get_me()
        if stop_event.is_set():
            return

        connection = await _connect_until_stopped(
            settings,
            stop_event=stop_event,
            connection_opener=connection_opener,
        )
        if connection is None:
            return

        consumer = consumer_factory(connection, telegram, settings, stop_event)
        try:
            await consumer.start()
            await _wait_for_stop_or_fatal(stop_event, consumer.fatal_event)
        except StartupCancelledError:
            return
        finally:
            try:
                await consumer.stop(drain_timeout=settings.telegram_shutdown_timeout)
            finally:
                await connection.close()

        if consumer.fatal_error is not None:
            raise consumer.fatal_error


async def _connect_until_stopped(
    settings: Settings,
    *,
    stop_event: asyncio.Event,
    connection_opener: ConnectionOpener,
) -> AbstractRobustConnection | None:
    """Разрешить SIGTERM прервать ожидание недоступного RabbitMQ."""
    connection_task: asyncio.Task[AbstractRobustConnection] = asyncio.create_task(
        connection_opener(settings)
    )
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {connection_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

    if stop_task in done:
        if connection_task in done and not connection_task.cancelled():
            connection = connection_task.result()
            await connection.close()
        await asyncio.gather(*pending, return_exceptions=True)
        return None

    await asyncio.gather(*pending, return_exceptions=True)
    return connection_task.result()


async def _wait_for_stop_or_fatal(
    stop_event: asyncio.Event,
    fatal_event: asyncio.Event,
) -> None:
    """Ждать внешний сигнал либо fatal consumer error."""
    stop_task = asyncio.create_task(stop_event.wait())
    fatal_task = asyncio.create_task(fatal_event.wait())
    _, pending = await asyncio.wait(
        {stop_task, fatal_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


async def run(settings: Settings) -> None:
    """Установить SIGINT/SIGTERM handlers на время жизни service."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(handled_signal, stop_event.set)
        except NotImplementedError:
            continue
        installed.append(handled_signal)

    try:
        await run_service(settings, stop_event=stop_event)
    finally:
        for handled_signal in installed:
            with suppress(NotImplementedError):
                loop.remove_signal_handler(handled_signal)


def main() -> int:
    """Загрузить настройки и вернуть безопасный process exit code."""
    try:
        settings = Settings()
    except Exception as error:
        # ValidationError содержит input values, поэтому печатается только класс.
        sys.stderr.write(
            f"telegram.worker_configuration_failed error_class={type(error).__name__}\n"
        )
        return 1

    configure_logging(level=settings.log_level, format_name=settings.log_format)
    try:
        asyncio.run(run(settings))
    except Exception as error:
        _logger.error(
            "telegram.worker_failed",
            telegram_status=getattr(error, "status_code", None),
            error_class=type(error).__name__,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
