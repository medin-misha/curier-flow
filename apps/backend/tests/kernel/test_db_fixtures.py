"""Страховка на саму обвязку базы: оба режима обязаны делать обещанное.

Без этих проверок обвязка может врать молча. Если бы вложенный режим на самом
деле коммитил, ни один тест не покраснел бы: чистка идёт перед тестом, и
чужие строки просто не дожили бы до проверки. Если бы схему по-прежнему
создавал `create_all`, забытая миграция снова стала бы незаметной.

Наблюдатель во всех проверках — отдельное соединение из движка. Только оно
показывает, что видно снаружи транзакции теста: сессия, живущая внутри неё,
видит собственные незакоммиченные строки в любом режиме.
"""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.kernel.db import session as session_module
from tests.models import Widget


async def _visible_from_outside(engine: AsyncEngine, name: str) -> int:
    """Сколько строк с таким именем видит соседнее соединение прямо сейчас.

    Считаются строки по имени, а не все подряд: тесты режима `clean_db`
    оставляют свои строки в базе, и снаружи они видны.
    """
    async with engine.connect() as outside:
        rows = select(func.count()).select_from(Widget).where(Widget.name == name)
        return await outside.scalar(rows) or 0


async def test_schema_comes_from_migrations(database: AsyncEngine) -> None:
    """В базе есть журнал Alembic: значит схему накатили миграции."""
    async with database.connect() as conn:
        revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))

    assert revision, "alembic_version is empty: the schema was not built by migrations"


async def test_test_only_tables_are_created_on_top(database: AsyncEngine) -> None:
    """Таблицы `tests/models.py` есть в базе, но их нет ни в одной миграции."""
    async with database.connect() as conn:
        found = await conn.scalar(text("SELECT to_regclass('public.test_widgets')"))

    assert found == "test_widgets"


async def test_nested_mode_does_not_reach_the_outside(
    session: AsyncSession,
    database: AsyncEngine,
) -> None:
    """Коммит внутри вложенного режима освобождает savepoint, а не пишет в базу."""
    async with session.begin():
        session.add(Widget(name="ghost"))

    assert await session.scalar(select(func.count()).select_from(Widget)) == 1
    assert await _visible_from_outside(database, "ghost") == 0


@pytest.mark.usefixtures("clean_db")
async def test_real_mode_commits_for_real(database: AsyncEngine) -> None:
    """Обратная страховка: в режиме `clean_db` коммит виден снаружи.

    Иначе тесты на гонки проверяли бы транзакции, которых нет.
    """
    async with session_module.session_factory() as db, db.begin():
        db.add(Widget(name="persisted"))

    assert await _visible_from_outside(database, "persisted") == 1
