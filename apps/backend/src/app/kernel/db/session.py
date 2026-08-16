"""Пул соединений, фабрика сессий и границы транзакций.

`engine` и `session_factory` — модульные синглтоны: пул соединений обязан быть
один на процесс, иначе каждый вызов создавал бы свой набор коннектов и
исчерпал лимит Postgres.

Границу транзакции задаёт зависимость, а не бизнес-код: одна транзакция на
запрос, коммит — при штатном выходе. Хендлеры и сервисы `commit()` не
вызывают никогда, иначе «атомарная» операция распадается на несколько,
а откат перестаёт откатывать.

Здесь же выполняются хуки «после коммита». Их регистрирует `events.bus`, но
исполнять их обязан владелец границы транзакции: «после коммита» — это момент
жизненного цикла транзакции, а не свойство шины событий.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.kernel.config import settings

#: Функция без аргументов, вызываемая после успешного коммита.
AfterCommitHook = Callable[[], Awaitable[None]]

#: Ключ в `session.info`, под которым копятся отложенные хуки. Хранить их в
#: самой сессии, а не в contextvar: хук привязан к конкретной транзакции, а в
#: одной задаче их может быть несколько подряд.
AFTER_COMMIT_HOOKS: Final = "app.after_commit_hooks"

_logger = structlog.get_logger("app.kernel.db.session")

engine: AsyncEngine = create_async_engine(
    str(settings.database_dsn),
    echo=settings.database_echo,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    # Соединение может умереть незаметно для пула: перезапуск Postgres,
    # таймаут pgbouncer, разрыв на NAT. Проверка перед выдачей стоит один
    # round-trip и снимает целый класс «первый запрос после простоя падает».
    pool_pre_ping=True,
)

#: expire_on_commit=False обязателен: иначе после коммита ORM помечает все
#: атрибуты просроченными, и сериализация ответа лезет за ними в БД уже вне
#: транзакции — в async-коде это MissingGreenlet, а не просто лишний запрос.
session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_uow() -> AsyncIterator[AsyncSession]:
    """Пишущая транзакция на запрос.

    `session.begin()` коммитит при штатном выходе из блока и откатывает при
    любом исключении, включая то, что подняла зависимость ниже по стеку.
    Упавший коммит поднимает исключение отсюда, из кода после `yield`.

    Само по себе это ещё не значит, что клиент узнает о неудаче: момент, в
    который веб-фреймворк закрывает зависимость, задаёт он, а не эта функция.
    Порядок «коммит → ответ» держится на объявлении зависимости в
    `app.api.deps`: `Depends(get_uow, scope="function")` закрывает генератор
    сразу после того, как обработчик маршрута вернул готовый ответ, но до его
    отправки. Область по умолчанию (`request`) закрывает его после отправки —
    и тогда исключение с коммита достаётся только логу, а клиент уже получил
    2xx на несохранённые данные. Ту же границу обязан ставить любой другой
    вызывающий: в тестах и скриптах это `asynccontextmanager(get_uow)`, где
    выход из блока и есть коммит.

    Хуки `after_commit` выполняются строкой ниже блока транзакции — то есть
    только если коммит состоялся. При исключении управление уходит из
    генератора прямо из `yield`, и до хуков дело не доходит: побочный эффект
    откатившейся транзакции выполняться не должен.
    """
    async with session_factory() as session:
        async with session.begin():
            yield session
        await _run_after_commit_hooks(session)


async def get_ro_session() -> AsyncIterator[AsyncSession]:
    """Сессия для чтения: транзакция явно не открывается.

    Читающему запросу не нужна граница транзакции, а её отсутствие означает,
    что коммитить нечего. Выход из блока закрывает сессию, а закрытие
    откатывает всё, что могло случайно накопиться в её identity map.
    """
    async with session_factory() as session:
        yield session


async def _run_after_commit_hooks(session: AsyncSession) -> None:
    """Выполнить хуки, накопленные `events.bus.after_commit`, по очереди.

    Хуки предназначены для эффектов, потерю которых бизнес переживёт (прогрев
    кеша, метрика), поэтому упавший хук только пишется в лог: он не имеет
    права ни испортить уже сформированный ответ, ни помешать соседним хукам.
    Всё, что терять нельзя, идёт через outbox, а не сюда.

    Список забирается из сессии, а не копируется: повторный вход (или
    несколько транзакций в одной сессии) не должен выполнить хук дважды.
    """
    hooks: list[AfterCommitHook] = session.info.pop(AFTER_COMMIT_HOOKS, [])
    for hook in hooks:
        try:
            await hook()
        except Exception:
            _logger.exception(
                "after_commit.hook_failed",
                hook=getattr(hook, "__qualname__", repr(hook)),
            )
