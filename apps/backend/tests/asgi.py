"""Тестовое приложение и клиенты к нему.

Сборка одна на весь прогон: `app_client` собирает приложение тем же
`create_app`, что и прод, из переданного набора модулей. Иначе каждый файл
тестов заводил бы свою сборку, и различия между ними — пройден ли lifespan,
подменены ли зависимости — оказывались бы незаметной причиной расхождений
между тестами.

`overrides` — штатный способ подменить зависимость: сессию, клиент проверок,
что угодно ещё, объявленное через `Depends`. Подмена живёт в самом
приложении, поэтому не протекает в соседние тесты, в отличие от правки
глобалей процесса.

`ASGITransport` вызывает приложение напрямую, поэтому тесты HTTP-слоя не
поднимают сервер, не занимают порт и не зависят от таймингов сети. Проверяется
при этом та же цепочка middleware и обработчиков ошибок, что и в проде, —
этого хватает почти всем тестам.

Не хватает его там, где важен сам момент отправки ответа: `ASGITransport`
собирает ответ целиком и только потом решает, что делать с исключением,
случившимся после его отправки, поэтому «клиент уже получил 2xx» и «клиент
получил 500» на нём неразличимы. Для таких проверок есть `live=True` —
настоящий uvicorn на эфемерном порту.
"""

import asyncio
import socket
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.kernel.registry import Module
from app.main import create_app

#: Объект, объявленный в `Depends(...)`: и подменяемая зависимость, и её замена.
Dependency = Callable[..., Any]


def build_app(
    modules: Sequence[Module] = (),
    *,
    overrides: Mapping[Dependency, Dependency] | None = None,
) -> FastAPI:
    """Собрать приложение из указанных модулей с подменёнными зависимостями.

    Принимает набор манифестов и словарь «зависимость → замена», возвращает
    готовое приложение. Отдельно от `app_client` — тестам, которым нужен сам
    объект приложения (схема OpenAPI, маршруты), клиент ни к чему.
    """
    app = create_app(modules)
    app.dependency_overrides.update(overrides or {})
    return app


@asynccontextmanager
async def app_client(
    modules: Sequence[Module] = (),
    *,
    overrides: Mapping[Dependency, Dependency] | None = None,
    lifespan: bool = False,
    live: bool = False,
    raise_app_exceptions: bool = True,
) -> AsyncIterator[AsyncClient]:
    """Клиент к приложению из указанных модулей.

    `lifespan=True` проходит жизненный цикл приложения: нужен модулям, чьи
    ручки читают созданное на старте (клиенты проверок, объектное хранилище).
    По умолчанию lifespan не запускается — большинству тестов он только стоил
    бы соединений с внешним миром.

    `live=True` поднимает настоящий uvicorn вместо прямого вызова приложения:
    нужен там, где проверяется, что именно получил клиент, а не что вернул
    обработчик.

    `raise_app_exceptions=False` нужен там, где проверяется ответ на
    необработанное исключение: ServerErrorMiddleware отдаёт 500 и поднимает
    исключение дальше, чтобы его увидел сервер, и по умолчанию httpx повторяет
    его в тесте вместо того, чтобы вернуть ответ. На `live=True` не влияет:
    настоящий сервер и так превращает исключение в ответ.
    """
    app = build_app(modules, overrides=overrides)
    async with AsyncExitStack() as stack:
        if lifespan:
            await stack.enter_async_context(app.router.lifespan_context(app))
        opened = _live_server(app) if live else _asgi_client(app, raise_app_exceptions)
        yield await stack.enter_async_context(opened)


@asynccontextmanager
async def _asgi_client(app: FastAPI, raise_app_exceptions: bool) -> AsyncIterator[AsyncClient]:
    """Клиент, вызывающий приложение напрямую, без сокета."""
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


class _AnnouncingServer(uvicorn.Server):
    """Сервер, о готовности которого можно узнать ожиданием, а не опросом."""

    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self.ready = asyncio.Event()

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        self.ready.set()


@asynccontextmanager
async def _live_server(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Клиент к приложению, поднятому настоящим uvicorn.

    Сервер живёт на время блока и останавливается на выходе.

    Сокет создаётся здесь и передаётся серверу готовым: порт `0` выбирает ядро,
    поэтому параллельные прогоны не дерутся за номер, и между выбором порта и
    его занятием нет окна, в которое влезет чужой процесс.

    `log_config=None` обязателен: со своим конфигом uvicorn перенастроил бы
    логирование процесса, а его в тестах настраивает шаблон.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    server = _AnnouncingServer(uvicorn.Config(app, log_config=None))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await server.ready.wait()
        async with AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            yield client
    finally:
        server.should_exit = True
        await serving
        listener.close()
