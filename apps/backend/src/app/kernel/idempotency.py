"""Идемпотентность записи: таблица ключей и операции над ней.

Зачем это нужно
---------------
Клиент никогда не знает, что случилось с запросом, ответ на который он не
получил: обрыв мог произойти до того, как заказ создан, и после. Единственное
разумное поведение клиента — повторить запрос, а единственное разумное
поведение сервиса — узнать повтор и не создать второй заказ. Узнаёт он его по
заголовку `Idempotency-Key`, который клиент генерирует сам и повторяет
неизменным при ретраях.

Та же логика действует внутри сервиса. Доставка сообщений в шаблоне везде
at-least-once: релей outbox вправе опубликовать сообщение дважды, брокер вправе
доставить его дважды, консьюмер вправе упасть после эффекта и до подтверждения.
«Ровно один раз» на сети не существует, поэтому защита от повтора обязана быть
у получателя. Для сообщений её делает `platform/idempotency.py` по
`processed_messages`, для HTTP-запросов — этот модуль по `idempotency_keys`.
Механика одна и та же: строка с уникальным ключом, вставленная той же
транзакцией, что и сам эффект.

Почему модель живёт в ядре
--------------------------
`alembic/env.py` не имеет права импортировать слой `api`, а таблица обязана
попадать в autogenerate. Кроме того, идемпотентность записи — свойство всего
сервиса, а не отдельного модуля: две копии этой таблицы в разных модулях
означали бы две разные гарантии.

FastAPI-обвязка (чтение заголовка, воспроизведение ответа) живёт в
`app/api/idempotency.py`: ядру нельзя знать про HTTP, а метка `@idempotent`
здесь именно потому, что её ставит бизнес-модуль, которому импорт `api`
запрещён правилом слоёв.
"""

import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final, cast
from uuid import UUID

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import (
    CursorResult,
    Delete,
    Enum,
    LargeBinary,
    SmallInteger,
    String,
    delete,
    func,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base

#: Имя заголовка. Написание из чернового стандарта IETF (`Idempotency-Key`):
#: в HTTP регистр заголовка не важен, но именно это написание клиенты видят в
#: документации Stripe, Adyen и прочих, и придумывать своё незачем.
IDEMPOTENCY_KEY_HEADER: Final = "Idempotency-Key"

#: Предел длины ключа. UUID и ULID укладываются с запасом, а неограниченная
#: длина означала бы, что клиент управляет размером строки в нашей таблице.
MAX_KEY_LENGTH: Final = 255

#: Атрибут, которым `idempotent` помечает обработчик. Читает его сборка
#: приложения — имя объявлено один раз, чтобы стороны не разъехались.
IDEMPOTENT_ATTR: Final = "__idempotent__"

_logger = structlog.get_logger("app.kernel.idempotency")


class IdempotencyStatus(StrEnum):
    """Стадия обработки запроса, занявшего ключ.

    `in_progress` — ключ занят, воспроизводимого ответа под ним нет;
    `completed` — ответ сохранён, повтор получит его копию.

    Обе записи идут одной транзакцией, поэтому снаружи строка почти всегда
    видна как `completed`: незавершённую не видит никто, а упавший запрос
    откатывает её вместе с данными. `in_progress` остаётся у ответа, который
    невозможно сохранить (потоковый) — и повтор такого запроса получит 409,
    а не пустое тело.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class IdempotencyKey(Base):
    """Ключ идемпотентности и ответ, сохранённый под ним.

    Строка появляется той же транзакцией, что и данные запроса: либо в базе
    есть и заказ, и его ключ, либо нет ни того, ни другого. Иначе остаётся
    окно, в котором заказ уже создан, а ключ ещё нет, — и повтор в этом окне
    создаёт второй заказ, то есть ровно то, от чего защищались.
    """

    __tablename__ = "idempotency_keys"

    #: Ключ придумывает клиент, поэтому он же первичный: уникальность обязана
    #: проверяться базой, а не запросом «а есть ли такая строка» — между
    #: проверкой и вставкой помещается параллельный запрос.
    key: Mapped[str] = mapped_column(String(MAX_KEY_LENGTH), primary_key=True)

    #: Отпечаток запроса: метод, путь, действующее лицо и тело. Тот же ключ с
    #: другим отпечатком — ошибка клиента (переиспользовал ключ), а не повтор.
    request_hash: Mapped[str] = mapped_column(String(64))

    #: Хранится как VARCHAR, а не как нативный тип Postgres: новое состояние —
    #: это правка кода, а нативный enum потребовал бы ALTER TYPE, который не
    #: откатывается внутри транзакции миграции.
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(
            IdempotencyStatus,
            name="idempotency_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )

    #: HTTP-статус сохранённого ответа. Без него повтор создания вернул бы 200
    #: вместо 201, и клиент, различающий их, повёл бы себя иначе.
    response_status: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    #: Тело ответа байт в байт. Не JSONB: под ключом лежит ответ, а не
    #: документ, и повтор обязан вернуть ту же последовательность байтов —
    #: сериализация JSONB переставляет ключи и нормализует числа.
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)

    #: Заголовки ответа, кроме тех, что принадлежат конкретной передаче
    #: (`content-length`, `date`, идентификатор запроса). Без них повтор терял
    #: бы `Location` у создания и `Content-Type` у чего угодно.
    response_headers: Mapped[dict[str, str] | None] = mapped_column(JSONB, default=None)

    #: Индекс нужен уборке: её запрос — `WHERE created_at < ...`, и без индекса
    #: ночной DELETE читал бы таблицу целиком.
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class IdempotencySettings(BaseSettings):
    """Настройки хранения ключей идемпотентности."""

    model_config = SettingsConfigDict(
        env_prefix="idempotency_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Сколько часов ключ защищает от повтора. Это верхняя граница разумного
    #: ретрая: клиент, повторивший запрос через сутки, повторяет не сбой сети,
    #: а собственное намерение, и второй заказ здесь — правильный ответ.
    retention_hours: int = Field(default=24, ge=1)

    #: Когда запускается уборка, в формате cron (UTC).
    cleanup_cron: str = "23 4 * * *"


#: Единственный экземпляр настроек процесса.
idempotency_settings = IdempotencySettings()


def idempotent[Handler: Callable[..., Any]](handler: Handler) -> Handler:
    """Пометить обработчик как требующий `Idempotency-Key`.

    Принимает функцию-обработчик, возвращает её же нетронутой. Метку читает
    сборка приложения (`app.api.idempotency.install_idempotency`) и навешивает
    на маршрут занятие ключа и воспроизведение ответа.

    Метка, а не подключение на месте, по двум причинам. Первая: правило слоёв
    запрещает бизнес-модулю импортировать `api`, поэтому взять оттуда
    зависимость или класс маршрута он не может. Вторая: это уже принятый в
    шаблоне способ — `@subscribe` и `@schedule` тоже только помечают функцию,
    а связывает её с приложением сборка, то есть единственное место, где
    состав сервиса объявлен явно.
    """
    setattr(handler, IDEMPOTENT_ATTR, True)
    return handler


def is_idempotent(handler: object) -> bool:
    """Проверить, помечен ли обработчик как идемпотентный."""
    return getattr(handler, IDEMPOTENT_ATTR, False) is True


def request_digest(*, method: str, path: str, actor_id: UUID | None, body: bytes) -> str:
    """Посчитать отпечаток запроса для сверки при повторе.

    Принимает метод, путь, действующее лицо и сырое тело, возвращает hex-строку
    SHA-256 длиной 64 символа.

    В отпечаток входит не только тело. Метод и путь — потому что один ключ,
    отправленный на две разные ручки, это ошибка клиента, а не повтор.
    Действующее лицо — потому что ключи придумывают клиенты, и без него чужой
    подобранный ключ вернул бы чужой сохранённый ответ.

    Тело берётся сырыми байтами: разбор в JSON и обратно нормализовал бы
    порядок ключей и пробелы, то есть счёл бы повтором запрос, который клиент
    осознанно изменил.
    """
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"\0")
    digest.update(path.encode())
    digest.update(b"\0")
    digest.update(str(actor_id).encode())
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


async def find_key(session: AsyncSession, key: str) -> IdempotencyKey | None:
    """Найти строку ключа или вернуть None.

    Принимает сессию и ключ, возвращает строку. Читающая операция: занимает
    ключ не она, а `reserve_key`.
    """
    return await session.get(IdempotencyKey, key)


async def reserve_key(session: AsyncSession, *, key: str, request_hash: str) -> bool:
    """Занять ключ в текущей транзакции.

    Принимает открытую транзакцию, ключ и отпечаток запроса. Возвращает
    `True`, если ключ занят именно этим вызовом, и `False`, если он уже занят
    кем-то ещё.

    Гонку двух одновременных запросов разрешает не проверка «есть ли строка»,
    а сама вставка. `ON CONFLICT DO NOTHING` в конкурентной транзакции ждёт
    исхода соседней: если та закоммитилась, не вставляется ничего, и признаком
    служит пустой `RETURNING`. Ожидание здесь — не изъян, а суть: пока первый
    запрос не закончил, ответить на второй нечем.
    """
    reserved = await session.execute(
        insert(IdempotencyKey)
        .values(key=key, request_hash=request_hash, status=IdempotencyStatus.IN_PROGRESS)
        .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
        .returning(IdempotencyKey.key)
    )
    return reserved.first() is not None


async def store_response(
    session: AsyncSession,
    *,
    key: str,
    status: int,
    body: bytes,
    headers: Mapping[str, str],
) -> None:
    """Сохранить ответ под занятым ключом.

    Принимает ту же транзакцию, в которой ключ был занят, статус, тело и
    заголовки ответа. Ничего не возвращает.

    Вызывается до коммита, поэтому ответ, данные и ключ уезжают в базу вместе.
    Отдельная транзакция «дописать ответ после коммита» оставила бы окно, в
    котором данные уже есть, а воспроизвести ответ нечем.
    """
    await session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == key)
        .values(
            status=IdempotencyStatus.COMPLETED,
            response_status=status,
            response_body=body,
            response_headers=dict(headers),
        )
    )


async def release_key(session: AsyncSession, *, key: str) -> None:
    """Освободить ключ в текущей транзакции.

    Принимает транзакцию и ключ, ничего не возвращает. Нужен для неуспешного
    ответа: под ключом остаётся только удавшаяся операция, а повторить
    сорвавшуюся клиент вправе тем же ключом.
    """
    await session.execute(delete(IdempotencyKey).where(IdempotencyKey.key == key))


async def purge_expired_keys(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    retention: timedelta,
) -> int:
    """Удалить ключи старше срока хранения.

    Принимает фабрику сессий и срок хранения, возвращает число удалённых
    строк.

    Безопасна при параллельном запуске в нескольких воркерах: `DELETE` берёт
    блокировки построчно, а условие отбора со временем только расширяется —
    два прохода могут удалить разные части одного набора, но не помешать друг
    другу и не удалить лишнего.
    """
    cutoff = datetime.now(tz=UTC) - retention
    async with session_factory() as session, session.begin():
        # `execute` типизирован как `Result`, у которого нет `rowcount`; на DML
        # драйвер всегда возвращает `CursorResult`.
        result = cast("CursorResult[Any]", await session.execute(_purge_statement(cutoff)))
        deleted = result.rowcount

    if deleted:
        _logger.info("idempotency.purged", deleted=deleted, cutoff=cutoff.isoformat())
    return deleted


def _purge_statement(cutoff: datetime) -> Delete:
    """Удаление ключей, созданных раньше отсечки."""
    return delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff)
