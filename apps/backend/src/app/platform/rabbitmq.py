"""Транспорт RabbitMQ: соединение, топология, публикация, консьюмеры.

Здесь живёт всё общение с внешними сервисами, которыми мы не управляем:
исходящие сообщения и приём чужих. Наша собственная фоновая работа идёт через
TaskIQ (`app.platform.taskiq`) — это разные вещи, и смешивать их в одной
очереди значит потерять возможность масштабировать их по отдельности.

Топология объявляется из деклараций модулей (`TopologyDecl`), а не собирается
императивно на старте: состав обменов и очередей должен быть виден в манифесте
модуля, а не в порядке вызовов внутри воркера.

Схема повторов и «мёртвых» сообщений
------------------------------------
Для декларации с очередью `Q` выводятся производные сущности (см.
`derived_names`)::

    Q.dlx    (fanout) → Q.dlq                      «сюда сообщение не вернётся»
    Q.retry  (fanout) → Q.retry (x-message-ttl)    выдержка перед повтором
    Q.retry.return (fanout) → Q                    возврат в основную очередь

Основная очередь объявляется с `x-dead-letter-exchange = Q.dlx`. Туда сообщение
попадает не только по нашему `nack`, но и когда его выбросил сам брокер
(истёк TTL, переполнение `x-max-length`) — такие потери обязаны оказаться в
DLQ, а не в бесконечном цикле повторов, поэтому DLX очереди указывает именно на
`Q.dlx`.

Повтор — осознанное решение консьюмера, поэтому он делается явной публикацией.
Обработчик упал:

* если у декларации задан `retry_ttl_ms` и попытки не исчерпаны — сообщение
  публикуется в `Q.retry` со счётчиком +1 и подтверждается в основной очереди;
  очередь `Q.retry` держит его `retry_ttl_ms`, после чего брокер по истечении
  TTL отправляет его в `Q.retry.return`, а тот — обратно в `Q`;
* иначе — `nack(requeue=False)`, то есть в `Q.dlx` → `Q.dlq`, где сообщение
  ждёт человека. Если `dead_letter=False`, DLX у очереди нет и сообщение
  выбрасывается: это и означает выключенный флаг.

Возврат идёт через отдельный обмен `Q.retry.return`, а не через основной обмен
и не через `x-dead-letter-routing-key`: первый вариант продублировал бы
сообщение во все соседние очереди с пересекающимися ключами, второй — подменил
бы routing key сообщения именем очереди, и обработчик, разбирающий ключ, начал
бы видеть разное до и после повтора.

Счётчик попыток — собственный заголовок `x-retry-attempt`, а не `x-death`.
`x-death` считает пары «очередь + причина», ведёт себя по-разному для classic и
quorum очередей и меняется вместе с версией брокера; счётчик, который мы сами
кладём при каждой перепубликации, зависит только от нашего кода и читается
одинаково везде.

Идентификатор сообщения
-----------------------
Ключом дедупликации служит `message_id` сообщения. Наши публикации проставляют
туда id строки outbox; чужой отправитель кладёт что-то своё, а если не кладёт
ничего, aiormq подставляет случайный UUID сам — ему нужен ключ для publisher
confirms. Не-UUID идентификатор не отбрасывается: из него выводится
стабильный UUIDv5, иначе партнёр с ключами вида `INV-2024-0001` не смог бы
пользоваться защитой от повторов вовсе.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any, Final
from uuid import UUID, uuid5

import structlog
from aio_pika import DeliveryMode, ExchangeType, Message, connect_robust
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
    ConsumerTag,
)
from pydantic import AmqpDsn, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.config import settings as app_settings
from app.kernel.context import request_id
from app.kernel.registry import ConsumerDecl, TopologyDecl
from app.platform.idempotency import run_once

#: Заголовок со счётчиком повторов. Имя начинается с `x-`, как принято для
#: служебных заголовков AMQP, но принадлежит нам: брокер его не трогает.
RETRY_ATTEMPT_HEADER: Final = "x-retry-attempt"

#: Пространство имён, в котором чужой `message_id` превращается в UUID.
#: Константа зафиксирована навсегда: смена значения сделала бы уже обработанные
#: сообщения снова необработанными.
MESSAGE_KEY_NAMESPACE: Final = UUID("6b2f7f1e-2a4e-5f9c-9c1d-0b6a3d5f7c11")

_logger = structlog.get_logger("app.platform.rabbitmq")


class RabbitMQSettings(BaseSettings):
    """Настройки транспорта. Живут здесь, а не в ядре: их владелец — этот модуль."""

    model_config = SettingsConfigDict(
        env_prefix="rabbitmq_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dsn: AmqpDsn = AmqpDsn("amqp://guest:guest@localhost:5672/")

    #: Сколько раз сообщение вернётся в очередь через `Q.retry`, прежде чем
    #: уйдёт в DLQ. Общий предел, а не поле декларации: у повторов есть смысл
    #: только вместе с выдержкой `retry_ttl_ms`, и разводить два параметра по
    #: разным местам конфигурации незачем.
    max_retries: int = Field(default=5, ge=0)


#: Единственный экземпляр настроек процесса. Соединений на импорте не создаётся:
#: это только чтение окружения.
rabbitmq_settings = RabbitMQSettings()


class ConsumerConfigError(Exception):
    """Консьюмер объявлен на очереди, которой нет ни в одной декларации топологии.

    Поднимается на старте процесса: консьюмер, молча не подписавшийся на
    несуществующую очередь, выглядит работающим и теряет все сообщения.
    """


@dataclass(frozen=True, slots=True)
class DerivedNames:
    """Имена сущностей, выведённые из имени очереди.

    Формат имён принадлежит платформе, а не манифесту модуля: декларация
    называет только свою очередь, а как зовутся её DLQ и очередь выдержки —
    деталь реализации, которую нельзя разносить по вызовам.
    """

    dead_letter_exchange: str
    dead_letter_queue: str
    retry_exchange: str
    retry_queue: str
    retry_return_exchange: str


def derived_names(queue: str) -> DerivedNames:
    """Собрать имена производных сущностей для очереди.

    Принимает имя основной очереди, возвращает имена её DLX/DLQ и обвязки
    повторов. Обмен и очередь могут называться одинаково: в AMQP это разные
    пространства имён, и совпадение имени `Q.retry` читается как «одна и та же
    сущность с двух сторон».
    """
    return DerivedNames(
        dead_letter_exchange=f"{queue}.dlx",
        dead_letter_queue=f"{queue}.dlq",
        retry_exchange=f"{queue}.retry",
        retry_queue=f"{queue}.retry",
        retry_return_exchange=f"{queue}.retry.return",
    )


@asynccontextmanager
async def connection(dsn: str) -> AsyncIterator[AbstractRobustConnection]:
    """Открыть robust-соединение с брокером на время работы блока.

    Принимает DSN, отдаёт соединение, при выходе закрывает его. Кидает то, что
    поднял драйвер, если брокер недоступен. Ограничение по времени навешивает
    вызывающий через `asyncio.timeout`: у проверки готовности и у старта
    воркера терпение разное.

    Соединение создаётся только этим вызовом и никогда на импорте модуля:
    процесс uvicorn импортирует бизнес-модули, а держать в нём коннект к
    брокеру нельзя — фоновая работа живёт в воркере.

    `connect_robust`, а не `connect`: разрыв сети не должен требовать
    перезапуска процесса, драйвер переподключается сам и восстанавливает
    каналы и консьюмеры.
    """
    conn = await connect_robust(
        dsn,
        # Имя видно в веб-интерфейсе и в `rabbitmqctl list_connections`: без
        # него разбор «кто держит соединение» упирается в список IP-адресов.
        client_properties={"connection_name": app_settings.app_name},
    )
    try:
        yield conn
    finally:
        await conn.close()


def open_channel(conn: AbstractRobustConnection) -> AbstractChannel:
    """Канал с полными гарантиями публикации.

    Принимает соединение, возвращает ещё не открытый канал: его либо ждут
    (`await`), либо используют как контекстный менеджер, как принято в
    aio-pika. Единственное место, где заданы параметры канала, — иначе
    гарантии зависели бы от того, кто его открыл.

    `publisher_confirms` превращает `publish()` в ожидание подтверждения от
    брокера: без них публикация — это «записали в сокет», и падение брокера в
    ту же миллисекунду проходит незамеченным.

    `on_return_raises` делает ошибкой возврат сообщения, которому не нашлось
    очереди. По умолчанию aio-pika отдаёт такое сообщение в коллбэк, и релей
    outbox посчитал бы его опубликованным.
    """
    return conn.channel(publisher_confirms=True, on_return_raises=True)


async def declare_topology(channel: AbstractChannel, declarations: Sequence[TopologyDecl]) -> None:
    """Объявить обмены, очереди и связки из деклараций модулей.

    Принимает канал и список деклараций, ничего не возвращает. Кидает
    `aiormq.exceptions.ChannelPreconditionFailed`, если сущность уже
    существует с другими параметрами.

    Объявление идемпотентно: повторный запуск процесса с той же топологией
    ничего не меняет. Но смена параметров уже существующей очереди (durable,
    TTL, DLX) — не «обновление», а конфликт, и брокер закроет канал. Такие
    изменения делаются переименованием очереди либо руками при выкатке; молча
    подстраиваться под расхождение платформа не имеет права.
    """
    for decl in declarations:
        names = derived_names(decl.queue)
        exchange = await channel.declare_exchange(
            decl.exchange,
            ExchangeType(decl.exchange_type),
            durable=decl.durable,
        )
        arguments: dict[str, Any] = dict(decl.arguments)
        if decl.dead_letter:
            await _declare_dead_letter(channel, decl, names)
            arguments["x-dead-letter-exchange"] = names.dead_letter_exchange

        queue = await channel.declare_queue(decl.queue, durable=decl.durable, arguments=arguments)
        await queue.bind(exchange, decl.routing_key)

        if decl.retry_ttl_ms is not None:
            await _declare_retry(channel, decl, names, queue)


async def publish(
    channel: AbstractChannel,
    *,
    exchange: str,
    routing_key: str,
    body: bytes,
    message_id: str | None = None,
    headers: Mapping[str, Any] | None = None,
    content_type: str | None = None,
) -> None:
    """Опубликовать сообщение и дождаться подтверждения брокера.

    Принимает канал из `open_channel`, адрес (обмен и ключ) и тело. Ничего не
    возвращает. Кидает `aio_pika.exceptions.DeliveryError`, если брокер
    отверг публикацию или сообщение некуда маршрутизировать.

    `mandatory=True` (умолчание aio-pika) оставлено сознательно: сообщение,
    для которого не нашлось очереди, — это ошибка конфигурации, и она обязана
    быть видна публикующему, а не теряться молча. Превращает такой возврат в
    исключение `on_return_raises` канала.

    `delivery_mode=PERSISTENT` обязателен: непостоянное сообщение исчезает при
    перезапуске брокера, а всё, что мы публикуем, переживает его по контракту.
    """
    # ensure=False: passive-объявление обмена стоило бы round-trip на каждую
    # публикацию, а обмен уже объявлен `declare_topology` на старте процесса.
    target = await channel.get_exchange(exchange, ensure=False)
    await target.publish(
        Message(
            body,
            headers=dict(headers) if headers is not None else None,
            content_type=content_type,
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id,
            timestamp=datetime.now(tz=UTC),
        ),
        routing_key=routing_key,
    )


class ConsumerGroup:
    """Консьюмеры одного процесса: запуск, обработка сообщения, остановка.

    Группа, а не отдельный консьюмер: у остановки смысл только целиком —
    «перестать забирать новое и дождаться того, что уже в работе». Каждому
    консьюмеру отводится свой канал: `prefetch` в AMQP настраивается на канал,
    а ошибка обработчика, закрывшая канал, не должна ронять соседей.

    Обработчик получает `(message, session)`: сырое сообщение брокера, потому
    что формат чужого сервиса платформе неизвестен, и открытую транзакцию,
    потому что отметка об идемпотентности обязана коммититься вместе с
    эффектом.
    """

    def __init__(
        self,
        conn: AbstractRobustConnection,
        consumers: Sequence[ConsumerDecl],
        topology: Sequence[TopologyDecl],
        *,
        session_factory: async_sessionmaker[AsyncSession],
        max_retries: int,
    ) -> None:
        self._connection = conn
        self._consumers = tuple(consumers)
        self._topology = {decl.queue: decl for decl in topology}
        self._session_factory = session_factory
        self._max_retries = max_retries
        self._subscriptions: list[tuple[AbstractQueue, ConsumerTag]] = []
        self._channels: list[AbstractChannel] = []
        self._in_flight = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._stopped = False

    async def start(self) -> None:
        """Подписаться на очереди всех консьюмеров.

        Ничего не принимает и не возвращает. Кидает `ConsumerConfigError`,
        если консьюмер объявлен на очереди, которой нет в топологии: платформа
        обязана знать её DLQ и параметры повторов, а «подписаться на всякий
        случай» означало бы обрабатывать сообщения без права на ошибку.
        """
        for decl in self._consumers:
            topology = self._topology.get(decl.queue)
            if topology is None:
                raise ConsumerConfigError(
                    f"Consumer for queue '{decl.queue}' has no TopologyDecl: declare the queue "
                    f"in Module.topology, otherwise the platform cannot tell where its dead "
                    f"letters and retries should go."
                )
            channel = await open_channel(self._connection)
            await channel.set_qos(prefetch_count=decl.prefetch)
            queue = await channel.get_queue(decl.queue)
            tag = await queue.consume(partial(self._on_message, decl, topology, channel))
            self._channels.append(channel)
            self._subscriptions.append((queue, tag))
            _logger.info("rabbitmq.consumer_started", queue=decl.queue, prefetch=decl.prefetch)

    async def stop(self, drain_timeout: float) -> None:
        """Перестать забирать сообщения и дождаться уже начатых.

        Принимает таймаут ожидания в секундах, ничего не возвращает. Повторный
        вызов ничего не делает: остановка вызывается и по сигналу, и при
        разматывании стека выхода.

        Сообщения, не успевшие обработаться за таймаут, не теряются: канал
        закрывается без подтверждения, и брокер возвращает их в очередь.
        Потерять можно только результат работы, которая шла дольше таймаута.
        """
        if self._stopped:
            return
        self._stopped = True

        for queue, tag in self._subscriptions:
            await queue.cancel(tag)
        _logger.info("rabbitmq.consumers_cancelled", in_flight=self._in_flight)

        try:
            await asyncio.wait_for(self._idle.wait(), drain_timeout)
        except TimeoutError:
            _logger.warning(
                "rabbitmq.shutdown_timed_out",
                in_flight=self._in_flight,
                timeout=drain_timeout,
            )

        for channel in self._channels:
            await channel.close()

    async def _on_message(
        self,
        decl: ConsumerDecl,
        topology: TopologyDecl,
        channel: AbstractChannel,
        message: AbstractIncomingMessage,
    ) -> None:
        """Обёртка вокруг обработки: учёт in-flight и контекст логов."""
        self._in_flight += 1
        self._idle.clear()
        token = request_id.set(_request_id_of(message))
        try:
            await self._dispatch(decl, topology, channel, message)
        finally:
            request_id.reset(token)
            self._in_flight -= 1
            if self._in_flight == 0:
                self._idle.set()

    async def _dispatch(
        self,
        decl: ConsumerDecl,
        topology: TopologyDecl,
        channel: AbstractChannel,
        message: AbstractIncomingMessage,
    ) -> None:
        """Обработать одно сообщение и решить его судьбу."""
        key = message_key(message) if decl.requires_idempotency else None
        if decl.requires_idempotency and key is None:
            # Дедупликация обещана декларацией, но дедуплицировать не по чему.
            # Повтор не поможет: идентификатор в сообщении не появится.
            _logger.error("rabbitmq.message_id_missing", queue=decl.queue)
            await message.nack(requeue=False)
            return

        try:
            await self._run_handler(decl, message, key)
        except Exception:
            _logger.exception("rabbitmq.handler_failed", queue=decl.queue)
            await self._recover(topology, channel, message)
            return

        await message.ack()

    async def _run_handler(
        self,
        decl: ConsumerDecl,
        message: AbstractIncomingMessage,
        key: UUID | None,
    ) -> None:
        """Вызвать обработчик — с защитой от повтора или без неё."""
        if key is None:
            async with self._session_factory() as session, session.begin():
                await decl.handler(message, session)
            return

        handled = await run_once(
            key,
            partial(decl.handler, message),
            session_factory=self._session_factory,
        )
        if not handled:
            _logger.info("rabbitmq.duplicate_skipped", queue=decl.queue, key=str(key))

    async def _recover(
        self,
        topology: TopologyDecl,
        channel: AbstractChannel,
        message: AbstractIncomingMessage,
    ) -> None:
        """Отправить упавшее сообщение на повтор либо в DLQ."""
        attempt = _retry_attempt(message)
        if topology.retry_ttl_ms is None or attempt >= self._max_retries:
            await message.nack(requeue=False)
            _logger.warning(
                "rabbitmq.message_dead_lettered",
                queue=topology.queue,
                attempt=attempt,
                dead_letter=topology.dead_letter,
            )
            return

        names = derived_names(topology.queue)
        await publish(
            channel,
            exchange=names.retry_exchange,
            routing_key=message.routing_key or topology.routing_key,
            body=message.body,
            message_id=message.message_id,
            headers={**message.headers, RETRY_ATTEMPT_HEADER: attempt + 1},
            content_type=message.content_type,
        )
        # Подтверждаем только после того, как повтор принят брокером: иначе
        # падение между ack и публикацией потеряло бы сообщение.
        await message.ack()
        _logger.info(
            "rabbitmq.message_retried",
            queue=topology.queue,
            attempt=attempt + 1,
            delay_ms=topology.retry_ttl_ms,
        )


async def _declare_dead_letter(
    channel: AbstractChannel,
    decl: TopologyDecl,
    names: DerivedNames,
) -> None:
    """Объявить обмен и очередь «мёртвых» сообщений.

    Обмен fanout: у DLQ ровно один источник, и маршрутизация по ключу здесь
    только повод ошибиться в имени ключа.
    """
    exchange = await channel.declare_exchange(
        names.dead_letter_exchange,
        ExchangeType.FANOUT,
        durable=decl.durable,
    )
    queue = await channel.declare_queue(names.dead_letter_queue, durable=decl.durable)
    await queue.bind(exchange)


async def _declare_retry(
    channel: AbstractChannel,
    decl: TopologyDecl,
    names: DerivedNames,
    main_queue: AbstractQueue,
) -> None:
    """Объявить обвязку повторов: обмен выдержки, очередь с TTL и обмен возврата."""
    return_exchange = await channel.declare_exchange(
        names.retry_return_exchange,
        ExchangeType.FANOUT,
        durable=decl.durable,
    )
    await main_queue.bind(return_exchange)

    retry_exchange = await channel.declare_exchange(
        names.retry_exchange,
        ExchangeType.FANOUT,
        durable=decl.durable,
    )
    retry_queue = await channel.declare_queue(
        names.retry_queue,
        durable=decl.durable,
        arguments={
            # TTL задан на очередь, а не на сообщение: сообщения в ней
            # протухают строго в порядке поступления, и голова очереди не
            # блокирует более поздние сообщения с меньшей выдержкой.
            "x-message-ttl": decl.retry_ttl_ms,
            "x-dead-letter-exchange": names.retry_return_exchange,
        },
    )
    await retry_queue.bind(retry_exchange)


def message_key(message: AbstractIncomingMessage) -> UUID | None:
    """Ключ дедупликации сообщения; `None`, если идентификатора нет вовсе.

    Принимает сообщение, возвращает UUID для `processed_messages`. Свой
    `message_id` разбирается как UUID; чужой формат сворачивается в UUIDv5 —
    отображение детерминированное, поэтому повторная доставка того же
    сообщения даёт тот же ключ, а разные идентификаторы не сталкиваются.

    `None` означает «дедуплицировать не по чему»: отправитель не проставил
    `message_id`. Такое сообщение платформа не обрабатывает — обещание
    «ровно один раз» выполнить нечем.
    """
    raw = message.message_id
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return uuid5(MESSAGE_KEY_NAMESPACE, raw)


def _retry_attempt(message: AbstractIncomingMessage) -> int:
    """Номер уже сделанной попытки повтора; 0 для первой доставки."""
    attempt = message.headers.get(RETRY_ATTEMPT_HEADER)
    return attempt if isinstance(attempt, int) else 0


def _request_id_of(message: AbstractIncomingMessage) -> str:
    """Идентификатор запроса из заголовков сообщения либо его `message_id`.

    Сообщение приходит из чужого процесса, и связать логи обработчика с логами
    отправителя можно только тем, что он положил в заголовок. Если не положил
    ничего — берём `message_id`: он хотя бы уникален и есть в логах брокера.
    """
    header = message.headers.get("request_id")
    if isinstance(header, str) and header:
        return header
    return message.message_id or "-"
