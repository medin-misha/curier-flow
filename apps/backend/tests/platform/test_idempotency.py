"""Однократное выполнение эффекта: отметка, откат, гонка потребителей, уборка."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db import session as session_module
from app.kernel.events.models import ProcessedMessage
from app.platform.idempotency import purge_processed_messages, run_once
from tests.models import Widget

pytestmark = pytest.mark.usefixtures("clean_db")


async def count_widgets() -> int:
    async with session_module.session_factory() as db:
        result = await db.execute(select(func.count()).select_from(Widget))
        return result.scalar_one()


async def count_marks() -> int:
    async with session_module.session_factory() as db:
        result = await db.execute(select(func.count()).select_from(ProcessedMessage))
        return result.scalar_one()


async def test_effect_runs_once_per_message() -> None:
    message_id = uuid4()
    calls: list[int] = []

    async def effect(db: AsyncSession) -> None:
        calls.append(1)
        db.add(Widget(name="bolt"))

    first = await run_once(message_id, effect, session_factory=session_module.session_factory)
    second = await run_once(message_id, effect, session_factory=session_module.session_factory)

    assert (first, second) == (True, False)
    assert len(calls) == 1
    assert await count_widgets() == 1
    assert await count_marks() == 1


async def test_different_messages_run_independently() -> None:
    async def effect(db: AsyncSession) -> None:
        db.add(Widget(name="bolt"))

    assert await run_once(uuid4(), effect, session_factory=session_module.session_factory)
    assert await run_once(uuid4(), effect, session_factory=session_module.session_factory)
    assert await count_widgets() == 2


async def test_failed_effect_rolls_back_the_mark() -> None:
    """Иначе повтор упавшего сообщения счёлся бы дубликатом и пропал."""
    message_id = uuid4()

    async def broken(db: AsyncSession) -> None:
        db.add(Widget(name="bolt"))
        raise RuntimeError("effect failed")

    with pytest.raises(RuntimeError, match="effect failed"):
        await run_once(message_id, broken, session_factory=session_module.session_factory)

    assert await count_marks() == 0
    assert await count_widgets() == 0

    async def repaired(db: AsyncSession) -> None:
        db.add(Widget(name="bolt"))

    assert await run_once(message_id, repaired, session_factory=session_module.session_factory)
    assert await count_widgets() == 1


async def test_concurrent_consumers_run_the_effect_once() -> None:
    """Два консьюмера получили одно сообщение одновременно."""
    message_id = uuid4()
    started = asyncio.Event()

    async def effect(db: AsyncSession) -> None:
        # Задержка внутри транзакции: соседняя попытка обязана дождаться
        # исхода этой, а не увидеть «отметки ещё нет».
        started.set()
        await asyncio.sleep(0.2)
        db.add(Widget(name="bolt"))

    results = await asyncio.gather(
        run_once(message_id, effect, session_factory=session_module.session_factory),
        run_once(message_id, effect, session_factory=session_module.session_factory),
    )

    assert started.is_set()
    assert sorted(results) == [False, True]
    assert await count_widgets() == 1
    assert await count_marks() == 1


async def test_purge_removes_old_marks_only() -> None:
    """Таблица растёт со скоростью всего потока сообщений и сама не убывает."""
    old, fresh = uuid4(), uuid4()
    async with session_module.session_factory() as db, db.begin():
        db.add_all([ProcessedMessage(message_id=old), ProcessedMessage(message_id=fresh)])
    async with session_module.session_factory() as db, db.begin():
        await db.execute(
            update(ProcessedMessage)
            .where(ProcessedMessage.message_id == old)
            .values(processed_at=datetime.now(tz=UTC) - timedelta(days=8))
        )

    deleted = await purge_processed_messages(
        session_factory=session_module.session_factory,
        retention=timedelta(days=7),
    )

    assert deleted == 1
    async with session_module.session_factory() as db:
        assert (await db.scalars(select(ProcessedMessage.message_id))).all() == [fresh]


async def test_purge_survives_a_parallel_run() -> None:
    """Периодическая задача может проснуться в двух воркерах сразу."""
    async with session_module.session_factory() as db, db.begin():
        db.add(ProcessedMessage(message_id=uuid4()))

    passes = await asyncio.gather(
        *(
            purge_processed_messages(
                session_factory=session_module.session_factory,
                retention=timedelta(seconds=0),
            )
            for _ in range(3)
        )
    )

    assert sum(passes) == 1
    assert await count_marks() == 0
