"""Точка входа Alembic: метаданные моделей и запуск миграций.

Пакеты моделей импортируются по реестру `MODULES`, а не ручным списком:
ручной список — это второй реестр, который забывают пополнить, и модуль
молча выпадает из autogenerate вместе со своими таблицами.

DSN берётся из настроек приложения, а не из alembic.ini: конфигурация
процесса одна, и миграции обязаны идти в ту же базу, куда ходит сервис.
"""

import asyncio
from importlib import import_module
from itertools import chain
from typing import Final

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.kernel.config import settings
from app.kernel.db.base import Base
from app.kernel.logging import configure_logging
from app.kernel.registry import iter_model_packages
from app.modules import MODULES

configure_logging()

#: Служебные таблицы принадлежат ядру, а не бизнес-модулю, поэтому в реестре
#: модулей их нет и `iter_model_packages` о них не знает. Без явного импорта их
#: не будет в метаданных, и autogenerate предложит удалить outbox из боевой
#: базы вместе с неопубликованными событиями, а `idempotency_keys` — вместе с
#: защитой от повторных запросов.
KERNEL_MODEL_PACKAGES: Final[tuple[str, ...]] = (
    "app.kernel.events.models",
    "app.kernel.idempotency",
)

for package in chain(KERNEL_MODEL_PACKAGES, iter_model_packages(MODULES)):
    import_module(package)

#: Модели должны быть импортированы до этой строки, иначе их таблиц не будет
#: в метаданных и autogenerate предложит удалить их из базы.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Сгенерировать SQL без подключения к базе (`alembic upgrade --sql`)."""
    context.configure(
        url=str(settings.database_dsn),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    """Выполнить миграции на открытом соединении.

    Синхронная функция: Alembic работает с синхронным API SQLAlchemy, и в
    async-режиме её прогоняют через `connection.run_sync`.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Без этих двух флагов autogenerate не заметит ни смену типа колонки,
        # ни смену server_default — миграция выйдет пустой, а схема разъедется.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Накатить миграции через async-движок.

    Движок создаётся свой, с NullPool: пул приложения переживает процесс и
    ему незачем открывать соединения ради одной короткой операции.
    """
    engine = create_async_engine(str(settings.database_dsn), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
