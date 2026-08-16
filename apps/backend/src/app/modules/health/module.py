"""Манифест модуля health и жизненный цикл его клиентов."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.kernel.registry import Module
from app.modules.health.handlers import router
from app.modules.health.services import (
    BROKER,
    BrokerProbe,
    HealthSettings,
    Probes,
    health_settings,
    probe,
)
from app.platform.rabbitmq import rabbitmq_settings
from app.platform.s3 import S3Settings, s3_settings, storage


def health_lifespan(
    *,
    broker_dsn: str,
    storage_config: S3Settings,
    timeouts: HealthSettings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Собрать lifespan модуля: клиенты, которыми пользуется readiness.

    Принимает адрес брокера, настройки хранилища и таймауты проверок,
    возвращает контекстный менеджер для манифеста.

    Фабрика, а не готовый lifespan: настройки передаются аргументами, поэтому
    тесты подставляют адреса своих контейнеров, не трогая глобальные настройки
    процесса.

    Клиенты создаются один раз на процесс и закрываются при остановке. На
    импорте модуля не создаётся ничего: импорт манифеста не должен открывать
    соединения — его делают и alembic, и воркер, которым readiness не нужен.

    Недоступность брокера или хранилища на старте приложению не мешает. Иначе
    readiness никогда не смог бы доложить о проблеме: контейнер просто не
    поднялся бы, и вместо «сервис не готов, брокер лежит» оркестратор увидел бы
    падающий под без объяснений.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            broker = BrokerProbe(broker_dsn)
            stack.push_async_callback(broker.aclose)
            # Создание клиента S3 сети не касается: соединение он откроет на
            # первом запросе. Поэтому лежащее хранилище старт не задерживает.
            object_storage = await stack.enter_async_context(storage(storage_config))

            app.state.health_probes = Probes(
                broker=broker,
                storage=object_storage,
                timeouts=timeouts,
            )
            # Тёплый старт: соединение с брокером открывается здесь, а не на
            # первом опросе readiness. Результат намеренно не влияет на старт —
            # готовность объявляет /health/ready, а не запуск процесса; неудачу
            # уже записал в лог сам `probe`.
            await probe(BROKER, broker.check, timeouts.broker_timeout)
            yield

    return lifespan


health_module: Final = Module(
    name="health",
    router=router,
    settings=HealthSettings,
    lifespan=health_lifespan(
        broker_dsn=str(rabbitmq_settings.dsn),
        storage_config=s3_settings,
        timeouts=health_settings,
    ),
)
