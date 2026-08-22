"""Обвязка тестов, которым нужна настоящая база.

SQLite не используется принципиально: шаблон опирается на JSONB, `SKIP LOCKED`
и `ON CONFLICT`, и «зелёные» тесты на другом диалекте означали бы только то,
что мы проверили не тот SQL. Поэтому — одноразовый Postgres в контейнере.

Схему в нём создаёт Alembic, а не `Base.metadata.create_all`. Это не
формальность: `create_all` строит схему по моделям, то есть по определению
согласован с ними, и забытая миграция обнаружилась бы только на выкатке.
Схема из миграций означает, что расхождение моделей и `alembic/versions/`
роняет прогон.

Таблицы `tests/models.py` в миграциях отсутствуют намеренно: это полигон для
проверки миксинов, CRUD и пагинации, и в `alembic/versions/` им не место —
иначе шаблон привёз бы пользователю миграцию с чужими таблицами. Они
создаются поверх накатанной схемы отдельным `create_all` по явному списку
(`TEST_ONLY_TABLES`), поэтому в autogenerate и `alembic check` не участвуют.

Как тесты попадают в этот контейнер. Контракт требует, чтобы `engine` и
`session_factory` были модульными синглтонами, то есть создавались на импорте
из настроек, а `get_uow` берёт фабрику из глобали в момент вызова. Значит
достаточно подменить обе глобали, когда адрес контейнера уже известен; правка
окружения до импорта тут не годится — `os.environ` в проекте запрещён
линтером. Подмена делает фикстура `database` и откатывает её на выходе. Тем же
способом на контейнер наводится `settings.database_dsn` на время накатывания
миграций: `alembic/env.py` читает адрес базы из настроек приложения.

═══════════════════════════════════════════════════════════════════════════
Два режима работы с базой. Выбирать осознанно.
═══════════════════════════════════════════════════════════════════════════

`session` (и `nested_transaction` под ним) — **вложенная транзакция с
откатом**. Соединение одно, на нём открыта внешняя транзакция, а
`session_factory` процесса подменена фабрикой, которая присоединяется к ней
через SAVEPOINT (`join_transaction_mode="create_savepoint"`). Коммит внутри
теста освобождает savepoint, а не пишет в базу; на выходе внешняя транзакция
откатывается целиком. Быстро и не оставляет следов. Годится, когда тесту
нужна просто рабочая сессия: CRUD, пагинация, миксины.

`clean_db` — **настоящие независимые транзакции**. `session_factory` смотрит
в движок, каждая транзакция коммитится по-настоящему, а таблицы чистятся
перед тестом. Это единственный режим, в котором проверяемы:

* релей outbox — он весь про `FOR UPDATE SKIP LOCKED` в двух параллельных
  сессиях, а на одном соединении блокировок не бывает;
* идемпотентность — гарантия держится на том, что вторая настоящая
  транзакция ждёт исхода первой;
* границы транзакции (`tests/test_session.py`) — во вложенном режиме
  «закоммитилось» и «не закоммитилось» неразличимы по определению;
* `tests/test_commit_before_response.py` — там поднят настоящий uvicorn в
  том же процессе, и запрос обязан дойти до настоящего COMMIT.

Чистим до теста, а не после: данные упавшего теста остаются в контейнере, и
их можно посмотреть, пока прогон не закончился. По той же причине чистит и
вложенный режим — предыдущий тест из режима `clean_db` мог оставить строки.

Фикстуры контейнера не autouse: тесты кодека курсора, ошибок и конфигурации
базы не касаются, и платить за них запуском Docker незачем. По той же причине
брокер и объектное хранилище живут в отдельных фикстурах: тестам ядра они не
нужны, и запрашивает их только тот, кто действительно ходит в сеть.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Final

import pytest
from aio_pika.abc import AbstractRobustConnection
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn, SecretStr
from sqlalchemy import Table, delete
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.community.minio import MinioContainer
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer
from testcontainers.community.redis import RedisContainer

from app.kernel.config import settings
from app.kernel.db import session as session_module
from app.kernel.db.base import Base
from app.kernel.events.models import OutboxMessage, ProcessedMessage
from app.kernel.idempotency import IdempotencyKey
from app.kernel.security.tokens import jwt_settings
from app.modules.storage.models import File, FileUploadStaging
from app.platform.rabbitmq import connection
from tests.models import Blob, Widget

#: Корень репозитория: отсюда берутся alembic.ini и каталог миграций. Пути
#: абсолютные, потому что часть тестов меняет рабочий каталог процесса.
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: Секрет подписи на время прогона. Дефолт шаблона (`change-me-in-production`)
#: короче 32 байт, и PyJWT предупреждает о слабом ключе HMAC на каждой подписи —
#: а предупреждения в прогоне настроены как ошибки. Подменяется поле общего
#: объекта настроек, чтобы код, читающий `jwt_settings` по имени модуля,
#: подписывал и проверял тем же секретом, что и тест.
TEST_JWT_SECRET: Final = SecretStr("0123456789abcdef0123456789abcdef")

#: Таблицы, которых нет и не должно быть в миграциях: они существуют только
#: ради тестов ядра. Создаются поверх накатанной схемы по этому списку.
TEST_ONLY_TABLES: Final[tuple[Table, ...]] = (
    Base.metadata.tables[Widget.__tablename__],
    Base.metadata.tables[Blob.__tablename__],
)

#: Модели, чьи таблицы чистятся перед каждым тестом. Перечислены явно: так тест
#: не начнёт молча зависеть от чужих таблиц, если метаданные пополнятся.
#: Таблицы ядра тоже здесь: outbox копится от теста к тесту, и «ровно одна
#: строка после коммита» без очистки проверить невозможно.
TEST_MODELS = (
    Widget,
    Blob,
    FileUploadStaging,
    File,
    OutboxMessage,
    ProcessedMessage,
    IdempotencyKey,
)


@pytest.fixture(autouse=True)
def signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подписывать и проверять токены секретом достаточной длины."""
    monkeypatch.setattr(jwt_settings, "secret", TEST_JWT_SECRET)


def _alembic_config() -> Config:
    """Конфигурация Alembic с абсолютными путями."""
    config = Config(REPO_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return config


def _migrate(dsn: str) -> None:
    """Накатить миграции на указанную базу.

    Адрес подставляется в общие настройки на время вызова: `alembic/env.py`
    сознательно берёт DSN оттуда, чтобы миграции шли в ту же базу, куда ходит
    сервис, и другого входа для адреса у него нет.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "database_dsn", PostgresDsn(dsn))
        command.upgrade(_alembic_config(), "head")


async def _create_test_only_tables(engine: AsyncEngine) -> None:
    """Добавить к накатанной схеме таблицы из `tests/models.py`."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=list(TEST_ONLY_TABLES))


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """Адрес одноразового Postgres на весь прогон."""
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def database(postgres_dsn: str) -> Iterator[AsyncEngine]:
    """Накатить схему и направить `engine` и `session_factory` ядра на контейнер.

    Миграции применяются один раз за прогон: контейнер один, а `upgrade head`
    на каждый тест стоил бы больше, чем всё остальное вместе.

    `NullPool` обязателен: pytest-asyncio даёт каждому тесту свой event loop,
    а соединение asyncpg привязано к тому циклу, в котором открыто. Без
    отключения пула второй тест получил бы соединение из чужого цикла.
    """
    _migrate(postgres_dsn)

    engine = create_async_engine(postgres_dsn, poolclass=NullPool)
    asyncio.run(_create_test_only_tables(engine))

    original_engine = session_module.engine
    original_factory = session_module.session_factory
    session_module.engine = engine
    session_module.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield engine
    session_module.engine = original_engine
    session_module.session_factory = original_factory
    asyncio.run(engine.dispose())


@pytest.fixture
async def clean_db(database: AsyncEngine) -> AsyncIterator[None]:
    """Пустые таблицы и настоящие транзакции: режим для проверок на гонки.

    Всё, что тест закоммитит, действительно окажется в базе и переживёт тест —
    поэтому чистка идёт перед следующим таким тестом, а не после текущего.
    """
    async with database.begin() as conn:
        for model in TEST_MODELS:
            await conn.execute(delete(model))
    yield


@pytest.fixture
async def nested_transaction(database: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Одно соединение с внешней транзакцией, которая откатится после теста.

    `session_factory` процесса подменяется фабрикой, привязанной к этому
    соединению: код под тестом, который берёт сессию сам, попадает в ту же
    транзакцию, а не в соседнюю. `join_transaction_mode="create_savepoint"`
    превращает его коммиты в освобождение SAVEPOINT — данные видны внутри
    теста и исчезают вместе с откатом внешней транзакции.

    Таблицы чистятся здесь же, внутри внешней транзакции: строки, оставленные
    тестами режима `clean_db`, мешали бы счётчикам, а откат вернёт их на место.
    """
    async with database.connect() as conn:
        transaction = await conn.begin()
        for model in TEST_MODELS:
            await conn.execute(delete(model))

        original_factory = session_module.session_factory
        session_module.session_factory = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield conn
        finally:
            session_module.session_factory = original_factory
            await transaction.rollback()


@pytest.fixture
async def session(nested_transaction: AsyncConnection) -> AsyncIterator[AsyncSession]:  # noqa: ARG001
    """Сессия для тестов, которые не проверяют сами границы транзакции."""
    async with session_module.session_factory() as db_session:
        yield db_session


@pytest.fixture(scope="session")
def rabbitmq_dsn() -> Iterator[str]:
    """Адрес одноразового RabbitMQ на весь прогон.

    Тот же образ, что и в docker compose: поведение x-message-ttl и
    dead-lettering зависит от версии брокера, и проверять их на другой было бы
    самообманом.
    """
    with RabbitMqContainer("rabbitmq:3-management-alpine") as container:
        params = container.get_connection_params()
        credentials = params.credentials
        yield (f"amqp://{credentials.username}:{credentials.password}@{params.host}:{params.port}/")


@pytest.fixture
async def broker(rabbitmq_dsn: str) -> AsyncIterator[AbstractRobustConnection]:
    """Соединение с брокером на один тест.

    Не на сессию: у каждого теста свой event loop, а соединение aiormq
    привязано к тому циклу, в котором открыто.
    """
    async with connection(rabbitmq_dsn) as conn:
        yield conn


@pytest.fixture(scope="session")
def minio_endpoint() -> Iterator[str]:
    """Адрес одноразового MinIO на весь прогон."""
    with MinioContainer() as container:
        yield f"http://{container.get_config()['endpoint']}"


@pytest.fixture(scope="session")
def redis_dsn() -> Iterator[str]:
    """Адрес одноразового Redis на весь прогон: result backend TaskIQ."""
    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        yield f"redis://{host}:{container.get_exposed_port(container.port)}/0"
