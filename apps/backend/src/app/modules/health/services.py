"""Проверки состояния сервиса и сводка о сборке.

Вся логика модуля живёт здесь: хендлеры только разбирают запрос и формируют
ответ. Проверки не поднимают соединения сами — долгоживущие клиенты создаёт
lifespan модуля и передаёт сюда аргументом. Readiness опрашивают раз в
несколько секунд, и соединение, открытое на каждый опрос, стоило бы дороже
самой проверки.

Модуль ничего не пишет и никуда не публикует: у него нет ни таблиц, ни
событий, ни задач. Проверка состояния, меняющая состояние, — это уже не
проверка.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from functools import partial
from typing import Final

import structlog
from aio_pika.abc import AbstractRobustConnection
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.config import settings
from app.platform.rabbitmq import connection, open_channel
from app.platform.s3 import ObjectStorage

#: Имена зависимостей в отчёте readiness. Константы, а не литералы по месту:
#: по этим именам мониторинг строит алерты, и опечатка в одном из трёх мест
#: тихо создала бы четвёртую «зависимость».
DATABASE: Final = "database"
BROKER: Final = "broker"
STORAGE: Final = "storage"

#: Предел длины причины отказа в ответе. Драйверы охотно вкладывают в текст
#: ошибки весь свой стек попыток, а readiness читают глазами и парсят
#: мониторингом — ни тому, ни другому килобайт текста не нужен.
_REASON_LIMIT: Final = 200

_logger = structlog.get_logger("app.modules.health")


class HealthSettings(BaseSettings):
    """Таймауты проверок готовности, в секундах.

    Таймаут у каждой зависимости свой: один зависший бэкенд не должен
    задерживать весь ответ, а разумное терпение к базе в соседней подсети и к
    объектному хранилищу за интернетом отличается.

    Значение подбирается под интервал опроса оркестратора: ответ readiness
    обязан успеть прийти раньше, чем придёт следующий запрос.
    """

    model_config = SettingsConfigDict(
        env_prefix="health_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_timeout: float = Field(default=2.0, gt=0)
    broker_timeout: float = Field(default=2.0, gt=0)
    storage_timeout: float = Field(default=2.0, gt=0)


#: Единственный экземпляр настроек процесса. Соединений на импорте не создаётся.
health_settings = HealthSettings()


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Результат проверки одной зависимости.

    `duration_ms` входит в отчёт не для красоты: зависимость, отвечающая за
    полторы секунды при таймауте в две, формально «up», а на деле уже лежит.
    Без времени такое видно только по факту отказа.
    """

    name: str
    up: bool
    duration_ms: float
    error: str | None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Отчёт о готовности сервиса целиком."""

    dependencies: tuple[DependencyStatus, ...]

    @property
    def ready(self) -> bool:
        """Готов ли сервис принимать трафик.

        Все зависимости обязательны: сервис, у которого отказала одна из них,
        отвечает ошибками на часть запросов, а балансировщику нужен ответ «да»
        или «нет», а не «частично».
        """
        return all(dependency.up for dependency in self.dependencies)


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """Сводка о сборке: что за сервис, какой версии и с какой схемой БД."""

    name: str
    version: str
    environment: str
    revision: str | None


class BrokerProbe:
    """Долгоживущее соединение с брокером, которым пользуется readiness.

    Класс, а не функция: между проверками нужно помнить соединение, а открывать
    его на каждый опрос запрещено — readiness дёргают раз в несколько секунд.

    Соединение восстанавливается лениво. Брокер, лежавший в момент старта
    процесса, не должен остаться «недоступным» навсегда: как только он
    поднимется, очередная проверка подключится и доложит об этом.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._stack = AsyncExitStack()
        self._connection: AbstractRobustConnection | None = None
        # Проверки readiness приходят от нескольких источников сразу
        # (оркестратор, балансировщик, мониторинг) и легко накладываются друг на
        # друга. Без замка каждая из них открыла бы своё соединение, а лишнее
        # осталось бы висеть в отброшенном AsyncExitStack и переподключаться
        # фоном до конца жизни процесса.
        self._lock = asyncio.Lock()

    async def check(self) -> None:
        """Убедиться, что брокер действительно отвечает.

        Ничего не принимает и не возвращает. Кидает то, что подняли драйвер или
        сеть; ограничение по времени навешивает вызывающий через
        `asyncio.timeout` — так же, как это делает воркер.

        Проверяется открытием канала, а не флагом `is_closed`: robust-соединение
        переподключается само и до первой неудачной операции считает себя живым,
        поэтому «не закрыто» не доказывает ничего. Открытие канала — настоящий
        round-trip к брокеру, и лежащий брокер на нём виден.
        """
        conn = await self._connected()
        async with open_channel(conn):
            pass

    async def aclose(self) -> None:
        """Закрыть текущее соединение. Повторный вызов безопасен."""
        async with self._lock:
            await self._drop()

    async def _connected(self) -> AbstractRobustConnection:
        """Вернуть соединение, открыв новое, если прежнего нет.

        Замок держится на всё время подключения, а не только на проверке флага:
        соединение открывается с ожиданием, и без взаимного исключения две
        одновременные проверки успели бы завести по своему.
        """
        async with self._lock:
            current = self._connection
            if current is not None and not current.is_closed:
                return current
            await self._drop()
            conn = await self._stack.enter_async_context(connection(self._dsn))
            self._connection = conn
            return conn

    async def _drop(self) -> None:
        """Закрыть соединение и завести пустой стек под следующее.

        Вызывается только под замком: замена `_stack` во время чужого
        подключения потеряла бы ссылку на уже открытое соединение.
        """
        self._connection = None
        await self._stack.aclose()
        self._stack = AsyncExitStack()


@dataclass(frozen=True, slots=True)
class Probes:
    """Клиенты и таймауты, которыми пользуется проверка готовности.

    Собираются один раз в lifespan модуля и живут до остановки процесса.
    """

    broker: BrokerProbe
    storage: ObjectStorage
    timeouts: HealthSettings


async def check_readiness(session: AsyncSession, probes: Probes) -> ReadinessReport:
    """Опросить все зависимости и собрать отчёт.

    Принимает сессию только для чтения и клиенты проверок, возвращает отчёт по
    каждой зависимости. Не кидает: отказ зависимости — это содержание ответа,
    а не ошибка запроса.

    Проверки идут одновременно: последовательный опрос складывал бы таймауты, и
    три зависимости с двухсекундным терпением держали бы ответ шесть секунд —
    дольше, чем оркестратор ждёт ответа на readiness.
    """
    timeouts = probes.timeouts
    statuses = await asyncio.gather(
        probe(DATABASE, partial(_ping_database, session), timeouts.database_timeout),
        probe(BROKER, probes.broker.check, timeouts.broker_timeout),
        probe(STORAGE, partial(_ping_storage, probes.storage), timeouts.storage_timeout),
    )
    return ReadinessReport(dependencies=tuple(statuses))


async def probe(
    name: str,
    check: Callable[[], Awaitable[None]],
    timeout: float,  # noqa: ASYNC109
) -> DependencyStatus:
    """Выполнить одну проверку, измерив время и превратив любой сбой в статус.

    Принимает имя зависимости, корутину проверки и таймаут в секундах,
    возвращает статус. Ничего не кидает: readiness обязан ответить отчётом даже
    когда лежит всё сразу.

    ASYNC109 требует, чтобы таймаут навешивал вызывающий, — здесь это
    невозможно: `asyncio.timeout` снаружи отменил бы весь `gather`, а функция
    обязана вернуть «down» по одной зависимости и не тронуть остальные. Именно
    поэтому таймаут принимается аргументом и применяется внутри.

    Широкий `except Exception` здесь не «на всякий случай», а вся задача
    функции: способов отказать у сети столько же, сколько библиотек внизу, и
    свести их к одному статусу больше негде. `asyncio.CancelledError` не
    наследует `Exception` и проходит мимо — отменённый запрос не отказ
    зависимости.
    """
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            await check()
    except Exception as error:
        reason = _reason(error)
        _logger.warning("health.dependency_down", dependency=name, reason=reason)
        return DependencyStatus(
            name=name,
            up=False,
            duration_ms=_elapsed_ms(started),
            error=reason,
        )
    return DependencyStatus(name=name, up=True, duration_ms=_elapsed_ms(started), error=None)


async def build_info(session: AsyncSession) -> BuildInfo:
    """Собрать сводку о сборке сервиса.

    Принимает сессию только для чтения, возвращает имя, версию, окружение и
    текущую ревизию схемы. Не кидает: недоступная база оставляет ревизию
    пустой, но не лишает ответа — узнать версию сервиса нужно как раз тогда,
    когда что-то сломалось.
    """
    return BuildInfo(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        revision=await current_revision(session),
    )


async def current_revision(session: AsyncSession) -> str | None:
    """Ревизия схемы из таблицы `alembic_version`; `None`, если её не прочитать.

    Принимает сессию только для чтения, возвращает идентификатор ревизии.
    Ничего не кидает: и лежащая база, и ещё не накатанные миграции (таблицы
    нет) — это штатные состояния для информационной ручки.

    Читается таблица Alembic, а не файлы миграций: интересует ревизия базы, в
    которую сервис ходит прямо сейчас, а не та, что лежит в его образе.
    """
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
    except Exception as error:
        _logger.warning("health.revision_unavailable", reason=_reason(error))
        return None
    revision = result.scalars().first()
    return str(revision) if revision is not None else None


async def _ping_database(session: AsyncSession) -> None:
    """Простейший запрос: пул выдал соединение и база на нём отвечает."""
    await session.execute(text("SELECT 1"))


async def _ping_storage(storage: ObjectStorage) -> None:
    """HEAD по бакету сервиса.

    Именно бакет, а не список бакетов: в проде у сервиса ключи с доступом
    только к своему бакету, и `ListAllMyBuckets` вернул бы им AccessDenied.
    Заодно проверка ловит опечатку в имени бакета и права на него, а не только
    то, что хранилище отзывается.
    """
    await storage.client.head_bucket(Bucket=storage.bucket)


def _elapsed_ms(started: float) -> float:
    """Сколько миллисекунд прошло с отметки `time.perf_counter()`."""
    return round((time.perf_counter() - started) * 1000, 3)


def _reason(error: BaseException) -> str:
    """Короткое описание отказа: тип исключения и его сообщение.

    Тип обязателен: у `TimeoutError` сообщения нет вовсе, и без имени класса
    причина отказа выглядела бы как пустая строка.
    """
    name = type(error).__name__
    message = " ".join(str(error).split())
    if not message:
        return name
    return f"{name}: {message[:_REASON_LIMIT]}"
