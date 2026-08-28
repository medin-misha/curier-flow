"""Точка входа HTTP-контейнера, которым управляет infra Compose.

Процесс uvicorn обслуживает только HTTP. Консьюмеры RabbitMQ, задачи TaskIQ и
релей outbox живут в `worker.py`: фоновая работа в веб-процессе умирает вместе
с ним при перекатке и масштабируется вместе с числом воркеров uvicorn.
"""

from collections.abc import Sequence

from fastapi import FastAPI

from app.api.authentication import install_authentication
from app.api.errors import install_error_handlers
from app.api.idempotency import install_idempotency
from app.api.middleware import RequestContextMiddleware
from app.api.router import build_router
from app.kernel.config import settings
from app.kernel.logging import configure_logging
from app.kernel.registry import Module, build_lifespan
from app.modules import MODULES


def create_app(modules: Sequence[Module] = MODULES) -> FastAPI:
    """Собрать ASGI-приложение из реестра модулей.

    Фабрика, а не готовый объект на уровне модуля: тесты собирают приложение
    со своим набором модулей, не трогая глобальный реестр.

    `debug` в FastAPI не передаётся сознательно: в режиме отладки Starlette
    отдаёт HTML-трейсбек вместо ответа обработчика ошибок, а формат ответа
    обязан быть один во всех окружениях. Подробности всегда уходят в лог.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        # Схема описывает всю поверхность API, включая служебные ручки,
        # поэтому вне отладки она и её просмотрщики закрыты.
        openapi_url="/openapi.json" if settings.debug else None,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=build_lifespan(modules),
    )
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(build_router(modules))
    install_authentication(app)
    # После include_router: он пересоздаёт маршруты по их публичным атрибутам,
    # и правка, сделанная раньше, до приложения бы не доехала.
    install_idempotency(app)
    return app


configure_logging()

#: ASGI-приложение для стадии api в Dockerfile. Собирается на импорте модуля.
app = create_app()
