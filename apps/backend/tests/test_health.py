"""Модуль health: liveness, readiness и информация о сборке.

Проверяется главное свойство пары live/ready: отказ зависимости обязан
опускать только readiness. Liveness при этом остаётся зелёным — иначе
оркестратор перезапустит контейнер вместо того, чтобы вывести его из
балансировки, и падение чужого сервиса превратится в цикл рестартов.
"""

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.kernel.config import settings
from app.kernel.db.session import get_ro_session
from app.main import create_app
from app.modules.health.module import health_lifespan, health_module
from app.modules.health.services import BrokerProbe, HealthSettings
from app.platform.s3 import S3Settings, storage
from tests.asgi import Dependency, app_client

#: Заведомо закрытый порт: соединение отвергается сразу, тест не ждёт таймаута.
UNREACHABLE_AMQP: Final = "amqp://guest:guest@127.0.0.1:1/"
UNREACHABLE_S3: Final = "http://127.0.0.1:1"
UNREACHABLE_POSTGRES: Final = "postgresql+asyncpg://app:app@127.0.0.1:1/app"

#: Терпение проверок в тестах меньше боевого: лежащая зависимость должна
#: отвечать отказом быстро, иначе прогон складывает таймауты.
TIMEOUTS: Final = HealthSettings(
    database_timeout=2.0,
    broker_timeout=2.0,
    storage_timeout=2.0,
)


@asynccontextmanager
async def running(
    *,
    broker_dsn: str,
    storage_config: S3Settings,
    overrides: dict[Dependency, Dependency] | None = None,
) -> AsyncIterator[AsyncClient]:
    """Клиент к приложению из одного модуля health с пройденным lifespan.

    Клиенты проверок создаёт lifespan модуля, поэтому он обязателен: без него
    `app.state.health_probes` пуст и readiness отвечать нечем.
    """
    module = dataclasses.replace(
        health_module,
        lifespan=health_lifespan(
            broker_dsn=broker_dsn,
            storage_config=storage_config,
            timeouts=TIMEOUTS,
        ),
    )
    async with app_client([module], lifespan=True, overrides=overrides) as client:
        yield client


def refuse_connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Запретить любой сетевой транспорт, вернув список попыток."""
    attempts: list[str] = []

    async def refuse(
        _self: asyncio.AbstractEventLoop,
        _protocol_factory: Callable[[], asyncio.BaseProtocol],
        host: str | None = None,
        port: int | None = None,
        **_kwargs: Any,
    ) -> None:
        attempts.append(f"{host}:{port}")
        raise AssertionError(f"unexpected connection to {host}:{port}")

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "create_connection", refuse)
    return attempts


def count_connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Считать открытые соединения, не мешая им открываться."""
    attempts: list[str] = []
    original: Any = asyncio.base_events.BaseEventLoop.create_connection

    async def counted(
        self: asyncio.AbstractEventLoop,
        protocol_factory: Callable[[], asyncio.BaseProtocol],
        host: str | None = None,
        port: int | None = None,
        **kwargs: Any,
    ) -> Any:
        attempts.append(f"{host}:{port}")
        return await original(self, protocol_factory, host, port, **kwargs)

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "create_connection", counted)
    return attempts


@pytest.fixture
async def bucket(minio_endpoint: str) -> AsyncIterator[S3Settings]:
    """Настройки хранилища с уже созданным бакетом на один тест."""
    config = S3Settings(endpoint_url=minio_endpoint, bucket=f"health-{uuid4().hex[:8]}")
    async with storage(config) as client:
        await client.client.create_bucket(Bucket=config.bucket)
    yield config


@pytest.fixture
async def stopped_postgres() -> AsyncIterator[dict[Dependency, Dependency]]:
    """Подмена сессии: она смотрит в закрытый порт, будто Postgres остановлен.

    Контейнер не гасится: он общий на весь прогон, а проверке безразлично,
    почему адрес не отвечает. Подменяется зависимость приложения, а не глобаль
    процесса: так поломка не переживает тест и видна прямо в его сборке.
    """
    engine = create_async_engine(UNREACHABLE_POSTGRES, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def dead_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    yield {get_ro_session: dead_session}
    await engine.dispose()


@pytest.fixture
def alembic_version(database: AsyncEngine) -> Iterator[str]:
    """Известная ревизия в таблице `alembic_version`.

    Схему тестовой базы накатывает Alembic, поэтому таблица уже есть и в ней
    лежит текущий head. Подменяется её значение, а не сама таблица: сравнивать
    ответ ручки с head нельзя — он меняется с каждой новой миграцией, и тест
    зеленел бы на любой строке, включая пустую.
    """
    revision = uuid4().hex[:12]

    async def read() -> str:
        async with database.begin() as conn:
            stored = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        return str(stored)

    async def write(value: str) -> None:
        async with database.begin() as conn:
            await conn.execute(
                text("UPDATE alembic_version SET version_num = :num"), {"num": value}
            )

    head = asyncio.run(read())
    asyncio.run(write(revision))
    yield revision
    asyncio.run(write(head))


def statuses(payload: dict[str, Any]) -> dict[str, str]:
    """Свести отчёт readiness к «зависимость → состояние»."""
    return {item["name"]: item["status"] for item in payload["dependencies"]}


async def test_live_answers_without_touching_any_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Liveness обязан отвечать, даже когда сеть недоступна целиком."""
    async with running(
        broker_dsn=UNREACHABLE_AMQP,
        storage_config=S3Settings(endpoint_url=UNREACHABLE_S3),
    ) as client:
        attempts = refuse_connections(monkeypatch)
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert attempts == []


async def test_live_is_up_and_ready_is_503_while_postgres_is_stopped(
    stopped_postgres: dict[Dependency, Dependency],
    rabbitmq_dsn: str,
    bucket: S3Settings,
) -> None:
    """Критерий этапа: упавшая база роняет readiness и не трогает liveness."""
    async with running(
        broker_dsn=rabbitmq_dsn, storage_config=bucket, overrides=stopped_postgres
    ) as client:
        alive = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert alive.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert statuses(ready.json()) == {"database": "down", "broker": "up", "storage": "up"}


async def test_ready_is_200_on_live_infrastructure(
    database: AsyncEngine,  # noqa: ARG001
    rabbitmq_dsn: str,
    bucket: S3Settings,
) -> None:
    async with running(broker_dsn=rabbitmq_dsn, storage_config=bucket) as client:
        response = await client.get("/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert statuses(payload) == {"database": "up", "broker": "up", "storage": "up"}
    assert all(item["error"] is None for item in payload["dependencies"])
    assert all(item["duration_ms"] > 0 for item in payload["dependencies"])


async def test_ready_is_503_when_the_broker_is_down(
    database: AsyncEngine,  # noqa: ARG001
    bucket: S3Settings,
) -> None:
    """Недоступный брокер обязан быть замечен, а не скрыт переподключением."""
    async with running(broker_dsn=UNREACHABLE_AMQP, storage_config=bucket) as client:
        response = await client.get("/health/ready")

    payload = response.json()
    broker = next(item for item in payload["dependencies"] if item["name"] == "broker")
    assert response.status_code == 503
    assert statuses(payload) == {"database": "up", "broker": "down", "storage": "up"}
    assert broker["error"]


async def test_ready_is_503_when_storage_is_down(
    database: AsyncEngine,  # noqa: ARG001
    rabbitmq_dsn: str,
) -> None:
    async with running(
        broker_dsn=rabbitmq_dsn,
        storage_config=S3Settings(endpoint_url=UNREACHABLE_S3),
    ) as client:
        response = await client.get("/health/ready")

    payload = response.json()
    storage_status = next(item for item in payload["dependencies"] if item["name"] == "storage")
    assert response.status_code == 503
    assert statuses(payload) == {"database": "up", "broker": "up", "storage": "down"}
    assert storage_status["error"]


async def test_ready_is_503_when_the_bucket_is_missing(
    database: AsyncEngine,  # noqa: ARG001
    rabbitmq_dsn: str,
    minio_endpoint: str,
) -> None:
    """Опечатка в имени бакета — тоже неготовность, а не «хранилище живо»."""
    async with running(
        broker_dsn=rabbitmq_dsn,
        storage_config=S3Settings(endpoint_url=minio_endpoint, bucket="never-created"),
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert statuses(response.json())["storage"] == "down"


async def test_application_starts_while_the_broker_is_down(
    database: AsyncEngine,  # noqa: ARG001
    bucket: S3Settings,
) -> None:
    """Лежащая зависимость не имеет права помешать старту процесса.

    Иначе readiness никогда не доложит о проблеме: контейнер не поднимется, и
    вместо внятного «брокер лежит» будет падающий под без объяснений.
    """
    async with running(broker_dsn=UNREACHABLE_AMQP, storage_config=bucket) as client:
        alive = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert alive.status_code == 200
    assert ready.status_code == 503


async def test_readiness_answers_are_not_cachable(
    database: AsyncEngine,  # noqa: ARG001
    rabbitmq_dsn: str,
    bucket: S3Settings,
) -> None:
    """Закешированный прокси 200 продолжит слать трафик в неготовый процесс."""
    async with running(broker_dsn=rabbitmq_dsn, storage_config=bucket) as client:
        ready = await client.get("/health/ready")
        alive = await client.get("/health/live")

    assert ready.headers["cache-control"] == "no-store"
    assert alive.headers["cache-control"] == "no-store"


async def test_broker_probe_reports_a_dead_address(rabbitmq_dsn: str) -> None:  # noqa: ARG001
    """Проверка обязана падать на нерабочем адресе, а не молчать."""
    probe = BrokerProbe(UNREACHABLE_AMQP)

    with pytest.raises(OSError):  # конкретный класс уточняет драйвер
        await probe.check()

    await probe.aclose()


async def test_broker_probe_keeps_one_connection_between_checks(
    rabbitmq_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness опрашивают раз в несколько секунд: соединение переиспользуется."""
    probe = BrokerProbe(rabbitmq_dsn)
    attempts = count_connections(monkeypatch)

    await probe.check()
    await probe.check()
    opened_after_reuse = len(attempts)

    # Потерянное соединение восстанавливается само: иначе брокер, лежавший в
    # момент старта, остался бы «недоступным» навсегда.
    await probe.aclose()
    await probe.check()
    await probe.aclose()

    assert opened_after_reuse == 1
    assert len(attempts) == 2


async def test_broker_probe_opens_one_connection_under_concurrent_checks(
    rabbitmq_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверки от разных источников накладываются, соединение остаётся одно.

    Без взаимного исключения каждая из одновременных проверок завела бы своё
    соединение, а лишние остались бы висеть и переподключаться фоном.
    """
    probe = BrokerProbe(rabbitmq_dsn)
    attempts = count_connections(monkeypatch)

    await asyncio.gather(*(probe.check() for _ in range(5)))
    await probe.aclose()

    assert len(attempts) == 1


async def test_info_reports_the_build_and_the_schema_revision(
    alembic_version: str,
    rabbitmq_dsn: str,
    bucket: S3Settings,
) -> None:
    async with running(broker_dsn=rabbitmq_dsn, storage_config=bucket) as client:
        response = await client.get("/health/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "revision": alembic_version,
    }


async def test_info_survives_a_stopped_database(
    stopped_postgres: dict[Dependency, Dependency],
    rabbitmq_dsn: str,
    bucket: S3Settings,
) -> None:
    """Версию сервиса надо узнать как раз тогда, когда что-то сломалось."""
    async with running(
        broker_dsn=rabbitmq_dsn, storage_config=bucket, overrides=stopped_postgres
    ) as client:
        response = await client.get("/health/info")

    assert response.status_code == 200
    assert response.json()["revision"] is None
    assert response.json()["version"] == settings.app_version


async def test_info_exposes_nothing_but_the_build(
    database: AsyncEngine,  # noqa: ARG001
    rabbitmq_dsn: str,
    bucket: S3Settings,
) -> None:
    """Ручка отвечает без аутентификации: в ней не должно быть ни адресов, ни ключей."""
    async with running(broker_dsn=rabbitmq_dsn, storage_config=bucket) as client:
        response = await client.get("/health/info")

    assert set(response.json()) == {"name", "version", "environment", "revision"}
    for secret in (rabbitmq_dsn, bucket.endpoint_url, bucket.access_key, bucket.secret_key):
        assert secret not in response.text


async def test_health_is_registered_in_the_application() -> None:
    """Модуль подключён к боевому приложению, а не только к тестовому."""
    paths = set(create_app().openapi()["paths"])

    assert {"/health/live", "/health/ready", "/health/info"} <= paths
