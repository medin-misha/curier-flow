"""Доменные события в брокере: публикация релея и доставка подписчикам.

Ядро сообщает, что факт произошёл, и не знает ни про AMQP, ни про обмены;
транспорт умеет возить байты и не знает про события. Здесь два контракта
встречаются: строка outbox превращается в сообщение брокера, а сообщение
брокера — в вызов подписчиков.

Отдельный модуль, а не часть `rabbitmq.py`: тот возит чужие сообщения, формат
которых нам неизвестен, и ничего не должен знать про `DomainEvent` и реестр
подписчиков.

Транзакция и ошибки подписчиков
-------------------------------
Всех подписчиков одного сообщения обслуживает одна транзакция — та же, в
которой стоит отметка `processed_messages` (её открывает `ConsumerGroup` через
`run_once`). Поэтому упавший подписчик откатывает и соседей, и отметку, а
сообщение возвращается в очередь и приезжает снова.

Альтернатива — ловить исключение каждого подписчика по отдельности — выглядит
терпимее, но означает частично применённое событие: два подписчика записали
свои данные, третий нет, и повторить его больше нечем, потому что отметка уже
стоит. Общий откат опирается на то, что доставка и так at-least-once, а
подписчики обязаны быть идемпотентны — тогда повтор безвреден, а расхождения
данных не возникает.

Событие, которое некому обработать
----------------------------------
Очередь связана с обменом по `#`, поэтому в неё попадают все события сервиса, в
том числе те, на которые в этом процессе никто не подписан. Отсутствие
подписчика — штатное состояние шаблона (`FileConfirmed` эмитится, слушать его
некому), а не сбой: обработать сообщение нечем, но и портить в нём нечего.
Такое сообщение подтверждается с записью уровня warning и в очередь несъедобных
не едет — иначе каждая штатная операция засоряла бы DLQ и поднимала алерт по
уровню error.

Несъедобные сообщения
---------------------
Полезная нагрузка, не подходящая под схему события, — не повод ронять воркер и
не повод повторять: от повтора она не исправится. Такое сообщение отправляется
в очередь несъедобных сразу и подтверждается: разбирать инцидент можно только
по сохранённому телу. Отметка об обработке при этом остаётся: сообщение
считается разобранным, и повторная доставка того же `message_id` не наплодит
копий в DLQ. Обратная сторона: ручной повтор из DLQ после выкатки исправленного
отправителя нужно делать с новым `message_id` — иначе он будет отброшен как
дубликат.
"""

from uuid import UUID

import structlog
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context import actor_id
from app.kernel.events.outbox import OutgoingEvent, Publish
from app.kernel.events.registry import EventRegistry
from app.platform.rabbitmq import publish

#: Тип полезной нагрузки события. Проставляется явно: потребитель, читающий
#: очередь руками, не должен угадывать формат по первому байту.
CONTENT_TYPE = "application/json"

_logger = structlog.get_logger("app.platform.domain_events")


def publisher(channel: AbstractChannel, exchange: str) -> Publish:
    """Собрать колбэк публикации для релея outbox.

    Принимает канал с подтверждениями публикации и имя обмена, возвращает
    корутину, которую релей вызывает на каждое событие.

    Ключ маршрутизации — топик события: обмен `topic`, поэтому подписку можно
    сузить до `order.*`, не трогая отправителя. `message_id` — идентификатор
    строки outbox: по нему потребитель отсеивает повторную доставку.
    """

    async def send(event: OutgoingEvent) -> None:
        await publish(
            channel,
            exchange=exchange,
            routing_key=event.topic,
            body=event.body,
            message_id=str(event.message_id),
            headers=event.headers,
            content_type=CONTENT_TYPE,
        )

    return send


async def deliver_to_subscribers(
    registry: EventRegistry,
    channel: AbstractChannel,
    dead_letter_exchange: str,
    message: AbstractIncomingMessage,
    session: AsyncSession,
) -> None:
    """Разобрать сообщение и отдать событие его подписчикам.

    Первые три аргумента подставляет воркер, последние два — `ConsumerGroup`.
    Ничего не возвращает. Пробрасывает исключение подписчика: транспортный
    слой обязан увидеть неудачу, откатить транзакцию и вернуть сообщение.

    Сообщение без подписчиков просто подтверждается, сообщение с неразбираемой
    нагрузкой уезжает в очередь несъедобных — см. докстринг модуля.

    Транзакция уже открыта и уже содержит отметку об обработке, поэтому
    подписчики получают именно её: их данные и отметка коммитятся вместе.
    """
    topic = message.routing_key or ""
    event_type = registry.event_for(topic)
    if event_type is None:
        _logger.warning("domain_events.no_subscribers", topic=topic, message_id=message.message_id)
        return

    try:
        event = event_type.model_validate_json(message.body)
    except ValidationError as error:
        _logger.error(
            "domain_events.invalid_payload",
            topic=topic,
            message_id=message.message_id,
            error=str(error),
        )
        await _park(channel, dead_letter_exchange, message)
        return

    # `request_id` восстанавливает ConsumerGroup, `actor_id` — здесь: он есть
    # только у наших сообщений, а чужому отправителю такой заголовок навязать
    # нельзя. Без него логи подписчика невозможно связать с автором действия.
    token = actor_id.set(_actor_of(message))
    try:
        for subscriber in registry.subscribers_for(event_type):
            await subscriber(event, session)
    finally:
        actor_id.reset(token)


async def _park(
    channel: AbstractChannel,
    exchange: str,
    message: AbstractIncomingMessage,
) -> None:
    """Переложить сообщение в очередь несъедобных как есть.

    Публикация, а не `nack(requeue=False)`: отклонить сообщение вправе только
    тот, кто его получил, — `ConsumerGroup`, — а он расценил бы исключение как
    сбой обработчика и сперва отправил бы сообщение на повторы, которым здесь
    взяться неоткуда.
    """
    await publish(
        channel,
        exchange=exchange,
        routing_key=message.routing_key or "",
        body=message.body,
        message_id=message.message_id,
        headers=message.headers,
        content_type=message.content_type,
    )


def _actor_of(message: AbstractIncomingMessage) -> UUID | None:
    """Действующее лицо из заголовков сообщения; `None`, если его там нет."""
    raw = message.headers.get("actor_id")
    if not isinstance(raw, str):
        return None
    try:
        return UUID(raw)
    except ValueError:
        _logger.warning("domain_events.bad_actor_id", value=raw)
        return None
