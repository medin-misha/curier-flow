"""Однократное выполнение эффекта для сообщения с заданным идентификатором.

Доставка в шаблоне везде at-least-once: и брокер, и релей outbox вправе
прислать одно и то же сообщение дважды. Единственная защита, которая
выдерживает падение процесса в произвольной точке, — отметка об обработке,
записанная той же транзакцией, что и сам эффект. Отметка в отдельной
транзакции (до или после) даёт окно, в котором эффект уже выполнен, а отметки
ещё нет, или наоборот, — и гарантия рвётся.

Модуль ничего не знает ни про AMQP, ни про доменные события: ему нужны
идентификатор сообщения и корутина, которой отдают открытую сессию. Поэтому он
живёт отдельно от `rabbitmq.py` — тот же вызов нужен доставке доменных событий
подписчикам, а она к транспорту отношения не имеет.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import CursorResult, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.events.models import ProcessedMessage

#: Эффект сообщения: корутина, получающая открытую транзакцию.
Effect = Callable[[AsyncSession], Awaitable[None]]

_logger = structlog.get_logger("app.platform.idempotency")


class ProcessedMessagesSettings(BaseSettings):
    """Настройки хранения отметок об обработанных сообщениях."""

    model_config = SettingsConfigDict(
        env_prefix="processed_messages_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Сколько дней хранится отметка. Она защищает только от повторной
    #: доставки, а повторы приходят в горизонте ретраев брокера и релея —
    #: часы, не месяцы. Хранить дольше значит платить за это индексом на
    #: таблице, которая растёт со скоростью всего потока сообщений.
    retention_days: int = Field(default=7, ge=1)

    #: Когда запускается уборка, в формате cron (UTC).
    cleanup_cron: str = "41 3 * * *"


#: Единственный экземпляр настроек процесса.
processed_messages_settings = ProcessedMessagesSettings()


async def run_once(
    message_id: UUID,
    effect: Effect,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """Выполнить эффект ровно один раз для этого `message_id`.

    Принимает идентификатор сообщения, корутину эффекта и фабрику сессий.
    Возвращает `True`, если эффект выполнен, и `False`, если это сообщение уже
    обработано раньше. Исключение эффекта пробрасывается наружу, откатывая и
    эффект, и отметку: неудачная попытка не должна выглядеть как выполненная.

    Гонку двух консьюмеров, получивших одно сообщение, разрешает не проверка
    «есть ли строка», а сама вставка: `ON CONFLICT DO NOTHING` в конкурентной
    транзакции ждёт исхода соседней и, если та закоммитилась, не вставляет
    ничего. Признаком служит `RETURNING`: строк нет — вставки не было. Считать
    `rowcount` было бы то же самое, но `RETURNING` не зависит от того, как
    драйвер разбирает тег команды.

    Фабрика сессий передаётся аргументом, а не берётся из ядра: вызывающий
    (консьюмер, релей, тест) обязан явно выбрать, в какой базе стоит отметка.
    """
    async with session_factory() as session, session.begin():
        marked = await session.execute(
            insert(ProcessedMessage)
            .values(message_id=message_id)
            .on_conflict_do_nothing(index_elements=[ProcessedMessage.message_id])
            .returning(ProcessedMessage.message_id)
        )
        if marked.first() is None:
            return False
        await effect(session)
    return True


async def purge_processed_messages(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    retention: timedelta,
) -> int:
    """Удалить отметки об обработке старше срока хранения.

    Принимает фабрику сессий и срок хранения, возвращает число удалённых
    строк.

    Уборка обязательна: таблица пополняется на каждое доставленное сообщение и
    не убывает сама. Отметка нужна ровно до тех пор, пока сообщение может
    прийти повторно, а после этого горизонта она защищает от повтора, которого
    уже не будет, ценой роста самой горячей служебной таблицы.

    Безопасна при параллельном запуске в нескольких воркерах: `DELETE` берёт
    блокировки построчно, а условие отбора со временем только расширяется.
    """
    cutoff = datetime.now(tz=UTC) - retention
    async with session_factory() as session, session.begin():
        # `execute` типизирован как `Result`, у которого нет `rowcount`; на DML
        # драйвер всегда возвращает `CursorResult`.
        result = cast(
            "CursorResult[Any]",
            await session.execute(
                delete(ProcessedMessage).where(ProcessedMessage.processed_at < cutoff)
            ),
        )
        deleted = result.rowcount

    if deleted:
        _logger.info("processed_messages.purged", deleted=deleted, cutoff=cutoff.isoformat())
    return deleted
