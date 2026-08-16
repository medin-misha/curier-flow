"""Манифест модуля и сборка приложения из реестра.

Реестр — единственный источник правды о составе сервиса: из него собираются
роутер, lifespan, метаданные Alembic, подписчики, расписание задач и топология
брокера. Автодискавери по файловой системе не делается намеренно: тогда состав
приложения зависел бы от результата обхода каталогов, и модуль подключался бы
или отваливался от одного переименования директории.

Типы веб-фреймворка импортируются только под `TYPE_CHECKING`. Ядро обязано
оставаться пригодным для воркера и миграций, где fastapi не нужен, поэтому
рантайм-импорта fastapi здесь нет, а сборка роутера живёт в `app.api.router`.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
    from contextlib import AbstractAsyncContextManager

    from fastapi import APIRouter, FastAPI
    from pydantic_settings import BaseSettings

#: Пустые аргументы очереди. MappingProxyType, а не литерал `{}`: значение по
#: умолчанию общее для всех деклараций, и случайная правка на месте разъехалась
#: бы по всей топологии.
_NO_ARGUMENTS: Final[Mapping[str, Any]] = MappingProxyType({})

#: Типы обмена RabbitMQ, которыми пользуется шаблон. `headers` не поддержан
#: намеренно: маршрутизация по заголовкам не нужна ни одному сценарию шаблона,
#: а объявить её позже дешевле, чем поддерживать неиспользуемую ветку.
ExchangeType = Literal["direct", "topic", "fanout"]


@dataclass(frozen=True, slots=True)
class TopologyDecl:
    """Очередь внешнего обмена вместе с её обвязкой.

    Одна декларация описывает связку exchange → binding → queue целиком:
    по отдельности эти сущности бессмысленны, а разнесённые по разным спискам
    они разъезжаются при первом же переименовании.

    `durable` один на обмен и очередь: долговечная очередь на недолговечном
    обмене (и наоборот) — это не конфигурация, а опечатка, и отдельный флаг
    только позволял бы её сделать.

    `arguments` — сырые аргументы очереди для того, что не выражается полями
    (`x-queue-type`, `x-max-length`). `dead_letter` включает DLX и очередь
    несъедобных сообщений, `retry_ttl_ms` — retry-обмен, возвращающий
    сообщение в основную очередь после выдержки. Имена производных сущностей
    выводит `platform/rabbitmq.py`: это его формат имён, а не часть манифеста.
    """

    exchange: str
    queue: str
    routing_key: str
    exchange_type: ExchangeType = "topic"
    durable: bool = True
    arguments: Mapping[str, Any] = _NO_ARGUMENTS
    dead_letter: bool = True
    retry_ttl_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ConsumerDecl:
    """Привязка «очередь → обработчик».

    `prefetch` задаётся на каждый консьюмер отдельно: у быстрых сообщений и у
    обработчика, ходящего в чужой API по секунде на сообщение, разумные
    значения отличаются на порядок, а общий лимит на процесс их усредняет.

    `requires_idempotency` — не документация, а указание платформенному слою
    обернуть обработчик проверкой по `processed_messages`. Доставка
    at-least-once, поэтому по умолчанию защита включена, а снимается она
    осознанно — для обработчиков, у которых повтор и так безвреден.
    """

    queue: str
    handler: Callable[..., Awaitable[None]]
    prefetch: int = 16
    requires_idempotency: bool = True


@dataclass(frozen=True, slots=True)
class Module:
    """Манифест бизнес-модуля: всё, что модуль отдаёт приложению.

    Модуль ничего не регистрирует сам и ни к чему не подключается на импорте:
    он только описывает себя, а подключение выполняет сборка приложения. Иначе
    состав сервиса зависел бы от того, какие модули кто-то успел импортировать.
    """

    name: str
    router: APIRouter | None = None
    prefix: str | None = None
    settings: type[BaseSettings] | None = None
    models: str | None = None
    subscribers: Sequence[Callable[..., Awaitable[None]]] = ()
    tasks: Sequence[Callable[..., Awaitable[Any]]] = ()
    consumers: Sequence[ConsumerDecl] = ()
    topology: Sequence[TopologyDecl] = ()
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None

    @property
    def url_prefix(self) -> str:
        """Префикс роутера модуля: заданный явно либо `/<name>`.

        Дефолт вычисляется здесь, а не в сборке роутера: адрес модуля нужен и
        тестам, и документации, и продублированное правило разъехалось бы.
        Пустая строка — валидное значение: так модуль вешает ручки в корень.
        """
        return f"/{self.name}" if self.prefix is None else self.prefix


def build_lifespan(
    modules: Sequence[Module],
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Собрать общий lifespan приложения из lifespan'ов модулей.

    Принимает реестр, возвращает контекстный менеджер для `FastAPI(lifespan=)`.

    `AsyncExitStack` здесь не украшение: модулей произвольное число, а если
    инициализация третьего упадёт, два уже поднятых обязаны закрыться в
    обратном порядке. Вложенными `async with` это не записать — их количество
    известно только в рантайме.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for module in modules:
                if module.lifespan is None:
                    continue
                await stack.enter_async_context(module.lifespan(app))
            yield

    return lifespan


def iter_model_packages(modules: Sequence[Module]) -> Iterator[str]:
    """Перечислить import-пути пакетов с ORM-моделями в порядке объявления.

    Возвращает пути, но не импортирует их: единственный потребитель —
    `alembic/env.py`, а ядро, дёргающее `import_module` на чужие пакеты,
    превращало бы собственный импорт в загрузку половины приложения.

    Повторы отбрасываются: два модуля вправе указать один и тот же пакет,
    и второй импорт того же пути ничего не добавит к метаданным.
    """
    seen: set[str] = set()
    for module in modules:
        if module.models is None or module.models in seen:
            continue
        seen.add(module.models)
        yield module.models
