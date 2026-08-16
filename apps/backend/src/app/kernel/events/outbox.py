"""Релей исходящих событий: публикация строк `outbox` и уборка за собой.

Транзакция сервиса кладёт событие в таблицу вместе с данными, а доставкой
занимается этот модуль — отдельным процессом и в своём темпе. Смысл разделения
в том, что запись события стоит ровно столько же, сколько запись самих данных,
и не зависит от того, жив ли брокер в момент запроса.

Публикация приходит аргументом-колбэком, а не берётся из `app.platform`: ядру
запрещено знать про aio-pika и обмены, и это не формальность — на ядро
опираются и миграции, и тесты. Проводку делает `worker.py`, единственное место,
где сходятся ядро и транспорт. Побочная выгода: релей проверяется без брокера.

Внешний вызов внутри транзакции
-------------------------------
Общее правило шаблона — «в транзакции только БД» — здесь нарушается осознанно.
Строка блокируется `FOR UPDATE SKIP LOCKED`, и блокировка обязана держаться до
конца публикации: отпусти её раньше — соседний релей заберёт ту же строку и
опубликует сообщение второй раз. Блокировка строчная, поэтому пишущие
транзакции (вставка новых событий) её не замечают: `INSERT` ни с чем не
конфликтует, а `SKIP LOCKED` не даёт ждать и самим релеям.

Отсрочка повторов
-----------------
Состав таблицы зафиксирован контрактом, колонки `next_attempt_at` в ней нет,
поэтому момент следующей попытки не хранится, а вычисляется в условии выборки
от `occurred_at`::

    возраст строки >= 0                                  при attempts = 0
    возраст строки >= min(base * 2^(attempts-1), cap)     при attempts > 0

Свойство «чем больше неудач, тем реже попытки» сохраняется: каждая неудача
удваивает возраст, при котором строка снова становится видимой. Первая попытка
отсрочки не получает — иначе каждое событие приезжало бы потребителю на `base`
секунд позже без всякой причины. Расписание никого не догоняет: после
восстановления брокера все просроченные строки видны сразу.

Судьба строки
-------------
* `published_at IS NULL` — ждёт публикации (возможно, с отсрочкой);
* `published_at` заполнен, `last_error IS NULL` — опубликовано штатно;
* `published_at` заполнен, `last_error` заполнен — попытки исчерпаны, сообщение
  отправлено в очередь несъедобных, а строка закрыта, чтобы релей не читал её
  вечно. Удалять её нельзя: это единственное место, где после инцидента видно,
  что именно не уехало и почему, — поэтому уборка такие строки не трогает.
"""

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from uuid import UUID

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import ColumnElement, CursorResult, Delete, Select, case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.events.models import OutboxMessage
from app.kernel.registry import TopologyDecl

#: Обмен доменных событий. Имена внутренней топологии — константы, а не
#: настройки: релей и консьюмер живут в разных местах кода и обязаны сойтись
#: на одном имени, а настройка добавляет ровно один новый способ ошибиться —
#: развести их разными значениями в разных процессах. Соседство с чужим
#: сервисом на одном брокере решается отдельным vhost, а не префиксом.
DOMAIN_EVENTS_EXCHANGE: Final = "domain.events"

#: Очередь подписчиков этого сервиса. Одна на процесс: доменные события —
#: внутренняя шина, и делить её на очереди по потребителям имеет смысл тогда,
#: когда у подписчиков разойдётся скорость обработки.
DOMAIN_EVENTS_QUEUE: Final = "domain.events.subscribers"

#: Выдержка перед повтором доставки подписчикам. Число повторов задаёт
#: `RABBITMQ_MAX_RETRIES`: повторы имеют смысл только парой «сколько раз» и
#: «через сколько», и разносить их по разным местам конфигурации незачем.
SUBSCRIBER_RETRY_TTL_MS: Final = 30_000

#: Топология доменных событий. Объявлена рядом с релеем, а не в манифесте
#: бизнес-модуля: события есть у любого сервиса на этом шаблоне, и очередь для
#: них — часть ядра, а не чья-то личная интеграция.
#:
#: Привязка по `#` — все топики в одну очередь. Альтернатива (связать только
#: известные топики) выглядит аккуратнее, но с `mandatory=True` превращает
#: событие без подписчиков в ошибку публикации: релей считал бы неудачей то,
#: что просто никому не нужно. Судьбу неизвестного топика решает консьюмер.
DOMAIN_EVENTS_TOPOLOGY: Final = TopologyDecl(
    exchange=DOMAIN_EVENTS_EXCHANGE,
    queue=DOMAIN_EVENTS_QUEUE,
    routing_key="#",
    exchange_type="topic",
    retry_ttl_ms=SUBSCRIBER_RETRY_TTL_MS,
)

_logger = structlog.get_logger("app.kernel.events.outbox")


class OutboxSettings(BaseSettings):
    """Настройки релея и уборки исходящих событий."""

    model_config = SettingsConfigDict(
        env_prefix="outbox_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Как часто просыпается релей, в секундах. Это же и есть задержка
    #: доставки события в худшем случае. Целое число не меньше секунды —
    #: дробные интервалы шедулер TaskIQ не принимает.
    relay_interval: int = Field(default=5, ge=1)

    #: Сколько строк релей забирает за один проход. Ограничение не столько по
    #: памяти, сколько по времени удержания блокировок: пачка публикуется в
    #: одной транзакции, и слишком большая держала бы соединение минутами.
    batch_size: int = Field(default=100, ge=1)

    #: После скольких неудачных публикаций сообщение уезжает в очередь
    #: несъедобных. С базовой отсрочкой в 5 секунд двенадцатая попытка
    #: приходится примерно на час жизни строки: недоступность брокера столько
    #: не живёт, а вот сообщение, которое брокер отвергает само по себе,
    #: перестаёт мешать очереди.
    max_attempts: int = Field(default=12, ge=1)

    #: Базовая отсрочка повтора в секундах: возраст, начиная с которого строка
    #: снова видна релею после первой неудачи.
    retry_base_delay: float = Field(default=5.0, ge=0)

    #: Потолок отсрочки в секундах. Страховка от переполнения при большом
    #: `max_attempts`, а не рабочий режим: при значениях по умолчанию попытки
    #: заканчиваются раньше, чем отсрочка дорастает до потолка.
    retry_max_delay: float = Field(default=3600.0, ge=0)

    #: Сколько дней хранятся опубликованные строки. Они нужны ровно для одного
    #: — доказать при разборе, что событие уехало, — и после этого срока
    #: занимают место в самой горячей таблице сервиса.
    retention_days: int = Field(default=7, ge=1)

    #: Когда запускается уборка. Ночь по UTC: `DELETE` по нескольким дням
    #: истории не должен совпадать с пиком нагрузки.
    cleanup_cron: str = "17 3 * * *"


#: Единственный экземпляр настроек процесса.
outbox_settings = OutboxSettings()


@dataclass(frozen=True, slots=True)
class OutgoingEvent:
    """Событие, готовое к отправке: всё, что нужно транспорту, и ничего больше.

    Ни обмена, ни ключа маршрутизации, ни свойств AMQP: ядро называет факт
    (`topic`) и отдаёт байты, а куда и как их положить, решает `platform`.
    """

    #: Он же `id` строки outbox: по нему потребитель отсеивает повтор.
    message_id: UUID
    topic: str
    body: bytes
    headers: Mapping[str, Any]


#: Отправка события во внешний мир. Колбэк, а не интерфейс: реализация ровно
#: одна (AMQP), а зависимость всё равно обязана быть инвертирована, потому что
#: ядру нельзя импортировать транспорт.
Publish = Callable[[OutgoingEvent], Awaitable[None]]


async def relay_outbox(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    publish: Publish,
    dead_letter: Publish,
    settings: OutboxSettings,
) -> int:
    """Опубликовать очередную пачку накопленных событий.

    Принимает фабрику сессий, колбэк публикации, колбэк отправки в очередь
    несъедобных и настройки. Возвращает число опубликованных строк. Ошибку
    публикации не поднимает: неудача — это запись в строке и в логе, а не
    падение периодической задачи.

    Безопасна при параллельном запуске в нескольких воркерах: строки берутся
    `FOR UPDATE SKIP LOCKED`, поэтому соседний релей не ждёт занятые и не
    забирает их себе.
    """
    async with session_factory() as session, session.begin():
        rows = (await session.scalars(_due_batch(settings))).all()
        published = await _publish_batch(
            rows,
            publish=publish,
            dead_letter=dead_letter,
            settings=settings,
        )

    if rows:
        _logger.info("outbox.relayed", selected=len(rows), published=published)
    return published


async def purge_published_events(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    retention: timedelta,
) -> int:
    """Удалить успешно опубликованные строки старше срока хранения.

    Принимает фабрику сессий и срок хранения, возвращает число удалённых
    строк.

    Строки, уехавшие в очередь несъедобных (`last_error` заполнен), не
    удаляются никогда: это материал для разбора инцидента, и решение об их
    судьбе принимает человек, а не расписание.
    """
    cutoff = datetime.now(tz=UTC) - retention
    async with session_factory() as session, session.begin():
        # `execute` типизирован как `Result`, у которого нет `rowcount`; на DML
        # драйвер всегда возвращает `CursorResult`, и это единственный способ
        # узнать число удалённых строк, не вычитывая их идентификаторы.
        result = cast("CursorResult[Any]", await session.execute(_purge_statement(cutoff)))
        deleted = result.rowcount

    if deleted:
        _logger.info("outbox.purged", deleted=deleted, cutoff=cutoff.isoformat())
    return deleted


def _purge_statement(cutoff: datetime) -> Delete:
    """Удаление опубликованных строк старше отсечки, кроме уехавших в DLQ."""
    return delete(OutboxMessage).where(
        OutboxMessage.published_at < cutoff,
        OutboxMessage.last_error.is_(None),
    )


def _due_batch(settings: OutboxSettings) -> Select[tuple[OutboxMessage]]:
    """Запрос очередной пачки: неопубликованные строки, которым пора.

    Порядок — `(occurred_at, id)`: он совпадает с частичным индексом таблицы,
    поэтому Postgres не досортировывает результат, и он же восстанавливает
    порядок событий одной транзакции, у которых `occurred_at` совпал.
    """
    return (
        select(OutboxMessage)
        .where(OutboxMessage.published_at.is_(None), _is_due(settings))
        .order_by(OutboxMessage.occurred_at, OutboxMessage.id)
        .limit(settings.batch_size)
        .with_for_update(skip_locked=True)
    )


def _is_due(settings: OutboxSettings) -> ColumnElement[bool]:
    """Условие «строка снова видна релею»: возраст перерос отсрочку.

    Считается от `occurred_at`, а не от времени последней попытки: колонки под
    неё в таблице нет, а разница между этими двумя способами — только в том,
    что здесь отсрочка накапливается с момента рождения события.
    """
    backoff = case(
        (OutboxMessage.attempts == 0, 0.0),
        else_=func.least(
            settings.retry_base_delay * func.pow(2.0, OutboxMessage.attempts - 1),
            settings.retry_max_delay,
        ),
    )
    age = func.extract("epoch", func.now() - OutboxMessage.occurred_at)
    return age >= backoff


async def _publish_batch(
    rows: Sequence[OutboxMessage],
    *,
    publish: Publish,
    dead_letter: Publish,
    settings: OutboxSettings,
) -> int:
    """Опубликовать пачку до первой неудачи и вернуть число уехавших строк.

    Первая же неудача останавливает проход: публикация падает почти всегда
    из-за транспорта, то есть одинаково для всех строк пачки, и упорство здесь
    означало бы `batch_size` бесполезных попыток с блокировками наперевес.
    Строка, упавшая по своей причине, соседей не задерживает — её собственная
    отсрочка убирает её из следующей выборки.
    """
    published = 0
    for row in rows:
        delivered = await _publish_row(
            row,
            publish=publish,
            dead_letter=dead_letter,
            settings=settings,
        )
        if not delivered:
            return published
        published += 1
    return published


async def _publish_row(
    row: OutboxMessage,
    *,
    publish: Publish,
    dead_letter: Publish,
    settings: OutboxSettings,
) -> bool:
    """Опубликовать одну строку; `False` — попытка не удалась."""
    try:
        await publish(_outgoing(row))
    except Exception as error:
        await _record_failure(row, error, dead_letter=dead_letter, settings=settings)
        return False

    row.published_at = datetime.now(tz=UTC)
    # Ошибка прошлой попытки больше не актуальна, а заполненный `last_error` у
    # опубликованной строки означает «уехало в DLQ» — см. докстринг модуля.
    row.last_error = None
    return True


async def _record_failure(
    row: OutboxMessage,
    error: Exception,
    *,
    dead_letter: Publish,
    settings: OutboxSettings,
) -> None:
    """Учесть неудачную публикацию и, если попытки исчерпаны, сдаться.

    Систему метрик шаблон не заводит, поэтому исчерпание попыток — отдельное
    структурное событие уровня error (`outbox.dead_lettered`) с топиком,
    идентификатором сообщения и числом попыток: по нему настраивается алерт,
    а до тех пор оно хотя бы видно в логе.

    Неудача отправки в очередь несъедобных оставляет строку неопубликованной.
    Это правильно: иначе событие исчезло бы совсем — ни в брокере, ни в
    ожидающих публикации.
    """
    row.attempts += 1
    row.last_error = _reason(error)
    _logger.warning(
        "outbox.publish_failed",
        message_id=str(row.id),
        topic=row.topic,
        attempts=row.attempts,
        error=row.last_error,
    )
    if row.attempts < settings.max_attempts:
        return

    try:
        await dead_letter(_outgoing(row))
    except Exception:
        _logger.exception(
            "outbox.dead_letter_failed",
            message_id=str(row.id),
            topic=row.topic,
        )
        return

    row.published_at = datetime.now(tz=UTC)
    _logger.error(
        "outbox.dead_lettered",
        message_id=str(row.id),
        topic=row.topic,
        attempts=row.attempts,
    )


def _outgoing(row: OutboxMessage) -> OutgoingEvent:
    """Собрать сообщение из строки outbox.

    Полезная нагрузка уже приведена к JSON-совместимым типам на стороне
    `emit()`, поэтому здесь остаётся только сериализация.
    """
    return OutgoingEvent(
        message_id=row.id,
        topic=row.topic,
        body=json.dumps(row.payload).encode(),
        headers=row.headers,
    )


def _reason(error: Exception) -> str:
    """Текст ошибки для колонки `last_error`.

    С типом исключения: у драйверов брокера сообщения бывают пустыми, и одна
    строка `''` в журнале неудач не сообщает ничего.
    """
    return f"{type(error).__name__}: {error}"
