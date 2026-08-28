"""Точка входа фонового контейнера, которым управляет infra Compose.

Один процесс на всю фоновую работу: воркер TaskIQ, его шедулер, консьюмеры
RabbitMQ и релей outbox. Разносить их по отдельным контейнерам имеет смысл
тогда, когда у них разойдётся профиль нагрузки; до тех пор четыре процесса
означали бы четыре пула соединений к БД и четыре места, где можно забыть
выкатить новую версию.

В процессе uvicorn ничего из этого не поднимается. Фоновая работа, привязанная
к веб-процессу, умирает вместе с ним при перекатке и размножается вместе с
числом его воркеров: периодическая задача начинает выполняться N раз.

Здесь же единственное место, где ядро соединяется с транспортом: релею
передаются колбэки публикации, а консьюмеру доменных событий — реестр
подписчиков. Ни ядро, ни платформа не знают друг о друге, поэтому проводка
обязана жить в точке входа.
"""

import asyncio
import signal
from collections.abc import Sequence
from contextlib import AsyncExitStack, suppress
from datetime import timedelta
from functools import partial
from typing import Final

import structlog
from aio_pika.abc import AbstractChannel
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.run import SchedulerLoop
from taskiq.receiver import Receiver

from app.kernel.db import session as db_session
from app.kernel.events.outbox import (
    DOMAIN_EVENTS_TOPOLOGY,
    outbox_settings,
    purge_published_events,
    relay_outbox,
)
from app.kernel.events.registry import EventRegistry, build_event_registry
from app.kernel.idempotency import idempotency_settings, purge_expired_keys
from app.kernel.logging import configure_logging
from app.kernel.registry import ConsumerDecl, Module, TopologyDecl
from app.modules import MODULES
from app.platform.domain_events import deliver_to_subscribers, publisher
from app.platform.idempotency import processed_messages_settings, purge_processed_messages
from app.platform.rabbitmq import (
    ConsumerGroup,
    connection,
    declare_topology,
    derived_names,
    open_channel,
    rabbitmq_settings,
)
from app.platform.taskiq import build_broker, build_scheduler, redis_settings, schedule

#: Имя манифеста системной части воркера. Не бизнес-модуль, но и не исключение
#: из правил: задачи, топология и консьюмеры подключаются в шаблоне только
#: через манифест, и заводить второй путь ради двух системных задач незачем.
#: Отсюда же берутся имена задач в очереди — `system.relay_outbox_events`.
SYSTEM_MODULE: Final = "system"

_logger = structlog.get_logger("app.worker")


class WorkerSettings(BaseSettings):
    """Настройки фонового процесса."""

    model_config = SettingsConfigDict(
        env_prefix="worker_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Сколько секунд ждать завершения уже начатой работы после SIGTERM.
    #: Значение подбирается под самый долгий обработчик и должно быть меньше
    #: таймаута оркестратора (у docker и kubernetes по умолчанию 30 секунд),
    #: иначе процесс добьют SIGKILL посреди обработки.
    shutdown_timeout: float = Field(default=30.0, gt=0)

    #: Сколько задач TaskIQ выполняется одновременно. Без предела воркер
    #: разбирает очередь настолько быстро, насколько её наполнили, и упирается
    #: не в себя, а в пул соединений к базе — с непонятными таймаутами вместо
    #: внятного отставания очереди.
    max_concurrent_tasks: int = Field(default=10, ge=1)


worker_settings = WorkerSettings()


def collect_topology(modules: Sequence[Module]) -> tuple[TopologyDecl, ...]:
    """Все декларации топологии реестра в порядке объявления модулей."""
    return tuple(decl for module in modules for decl in module.topology)


def collect_consumers(modules: Sequence[Module]) -> tuple[ConsumerDecl, ...]:
    """Все декларации консьюмеров реестра в порядке объявления модулей."""
    return tuple(decl for module in modules for decl in module.consumers)


def build_system_module(channel: AbstractChannel, registry: EventRegistry) -> Module:
    """Собрать манифест системной части: релей, уборка служебных таблиц, подписчики.

    Уборок три, и все они про одно: служебные таблицы (`outbox`,
    `idempotency_keys`, `processed_messages`) пополняются на каждую операцию
    сервиса и не убывают сами. Живут они здесь, а не в бизнес-модуле, потому
    что таблицы принадлежат ядру и платформе.

    Принимает канал публикации и реестр подписчиков, возвращает манифест,
    который добавляется к реестру модулей последним.

    Задачи объявлены замыканиями без аргументов: TaskIQ кладёт аргументы
    задачи в сообщение, а канал брокера и фабрику сессий в очередь не
    отправишь. Замыкание берёт их из процесса, а расписание — из настроек.
    """
    publish_event = publisher(channel, DOMAIN_EVENTS_TOPOLOGY.exchange)
    dead_letter_exchange = derived_names(DOMAIN_EVENTS_TOPOLOGY.queue).dead_letter_exchange

    @schedule(interval=timedelta(seconds=outbox_settings.relay_interval))
    async def relay_outbox_events() -> None:
        await relay_outbox(
            session_factory=db_session.session_factory,
            publish=publish_event,
            dead_letter=publisher(channel, dead_letter_exchange),
            settings=outbox_settings,
        )

    @schedule(cron=outbox_settings.cleanup_cron)
    async def purge_outbox_events() -> None:
        await purge_published_events(
            session_factory=db_session.session_factory,
            retention=timedelta(days=outbox_settings.retention_days),
        )

    @schedule(cron=idempotency_settings.cleanup_cron)
    async def purge_idempotency_keys() -> None:
        await purge_expired_keys(
            session_factory=db_session.session_factory,
            retention=timedelta(hours=idempotency_settings.retention_hours),
        )

    @schedule(cron=processed_messages_settings.cleanup_cron)
    async def purge_message_marks() -> None:
        await purge_processed_messages(
            session_factory=db_session.session_factory,
            retention=timedelta(days=processed_messages_settings.retention_days),
        )

    return Module(
        name=SYSTEM_MODULE,
        tasks=(
            relay_outbox_events,
            purge_outbox_events,
            purge_idempotency_keys,
            purge_message_marks,
        ),
        topology=(DOMAIN_EVENTS_TOPOLOGY,),
        consumers=(
            ConsumerDecl(
                queue=DOMAIN_EVENTS_TOPOLOGY.queue,
                handler=partial(
                    deliver_to_subscribers,
                    registry,
                    channel,
                    dead_letter_exchange,
                ),
            ),
        ),
    )


async def run_worker(modules: Sequence[Module] = MODULES) -> None:
    """Поднять фоновый процесс и работать до SIGTERM.

    Принимает реестр модулей, ничего не возвращает. Возвращает управление
    только после того, как остановлены консьюмеры, слит воркер TaskIQ и
    закрыты соединения.

    Порядок остановки важен: сперва перестаём забирать новые сообщения, потом
    ждём начатые и только затем закрываем соединения. Обратный порядок оборвал
    бы обработку на середине, и брокер вернул бы в очередь сообщения, часть
    эффектов которых уже применена.
    """
    shutdown = asyncio.Event()
    _install_signal_handlers(shutdown)

    timeout = worker_settings.shutdown_timeout
    # Реестр строится до единого соединения: ошибка в подписках модуля обязана
    # ронять процесс на старте, а не при первом пришедшем событии.
    registry = build_event_registry(modules)

    async with AsyncExitStack() as stack:
        conn = await stack.enter_async_context(connection(str(rabbitmq_settings.dsn)))
        # Канал публикации открыт всё время работы процесса: им пользуются
        # релей outbox и парковка несъедобных сообщений, а канал на каждую
        # публикацию — это лишняя пара round-trip к брокеру на сообщение.
        publisher_channel = await open_channel(conn)
        stack.push_async_callback(publisher_channel.close)

        all_modules = (*modules, build_system_module(publisher_channel, registry))
        topology = collect_topology(all_modules)
        consumer_decls = collect_consumers(all_modules)

        # Топология объявляется на отдельном канале: расхождение параметров
        # очереди закрывает канал, и рабочие каналы консьюмеров не должны
        # умирать вместе с ним.
        async with open_channel(conn) as channel:
            await declare_topology(channel, topology)

        broker = build_broker(
            all_modules,
            amqp_dsn=str(rabbitmq_settings.dsn),
            redis_dsn=str(redis_settings.dsn),
            result_ttl=redis_settings.result_ttl,
        )
        # Флаги читает сам TaskIQ: воркеру нужен канал на чтение очереди задач,
        # шедулеру — только на запись. Здесь один процесс делает и то, и другое.
        broker.is_worker_process = True
        broker.is_scheduler_process = True

        consumers = ConsumerGroup(
            conn,
            consumer_decls,
            topology,
            session_factory=db_session.session_factory,
            max_retries=rabbitmq_settings.max_retries,
        )
        await consumers.start()
        stack.push_async_callback(consumers.stop, timeout)

        await broker.startup()
        stack.push_async_callback(broker.shutdown)

        scheduler_task = asyncio.create_task(
            _run_scheduler(build_scheduler(broker)),
            name="taskiq.scheduler",
        )
        stack.push_async_callback(_cancel, scheduler_task)

        receiver = Receiver(
            broker=broker,
            # Брокер уже поднят выше: второй `startup()` открыл бы ещё пару
            # соединений и переобъявил очереди задач.
            run_startup=False,
            max_async_tasks=worker_settings.max_concurrent_tasks,
            wait_tasks_timeout=timeout,
        )
        worker_task = asyncio.create_task(receiver.listen(shutdown), name="taskiq.worker")

        _logger.info(
            "worker.started",
            modules=len(modules),
            consumers=len(consumer_decls),
            tasks=len(broker.get_all_tasks()),
        )

        await shutdown.wait()
        _logger.info("worker.stopping", timeout=timeout)
        await consumers.stop(timeout)
        await worker_task

    _logger.info("worker.stopped")


def main() -> None:
    """Запустить стадию worker из Dockerfile."""
    configure_logging()
    asyncio.run(run_worker())


async def _run_scheduler(scheduler: TaskiqScheduler) -> None:
    """Крутить цикл расписаний до отмены задачи.

    `scheduler.startup()` не вызывается намеренно: он поднимает брокер, а тот
    уже поднят процессом. Поднимаются только источники расписаний — именно они
    читают метки задач.

    `skip_first_run=True` помечает cron-задачи текущей минуты как уже
    выполненные: без этого перезапуск воркера в 12:00:30 повторно запустил бы
    всё, что стоит на `0 12 * * *`.
    """
    for source in scheduler.sources:
        await source.startup()
    loop = SchedulerLoop(scheduler, event_loop=asyncio.get_running_loop())
    try:
        await loop.run(skip_first_run=True)
    finally:
        for source in scheduler.sources:
            await source.shutdown()


async def _cancel(task: asyncio.Task[None]) -> None:
    """Отменить задачу и дождаться её завершения."""
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _install_signal_handlers(shutdown: asyncio.Event) -> None:
    """Связать SIGTERM и SIGINT с событием остановки.

    Обработчик только взводит событие: остальное делает `run_worker`. Работа
    из обработчика сигнала в asyncio выполняется в неопределённый момент между
    шагами цикла, и открывать оттуда транзакции или закрывать соединения
    нельзя.
    """
    loop = asyncio.get_running_loop()
    for received in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(received, shutdown.set)


if __name__ == "__main__":
    main()
