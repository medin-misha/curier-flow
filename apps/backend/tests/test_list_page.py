"""Keyset-пагинация против настоящего Postgres."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.pagination import PageParams
from tests.models import Blob, Widget
from tests.schemas import BlobCreate, WidgetCreate

BASE_MOMENT = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)


async def _fill(session: AsyncSession, timestamps: list[datetime]) -> list[Widget]:
    return [
        await CRUD.create(Widget, WidgetCreate(name=f"w{index}"), session, created_at=moment)
        for index, moment in enumerate(timestamps)
    ]


def _expected_order(widgets: list[Widget]) -> list[UUID]:
    """Порядок, который обязан вернуть ORDER BY created_at DESC, id DESC."""
    return [w.id for w in sorted(widgets, key=lambda w: (w.created_at, w.id), reverse=True)]


async def _walk(session: AsyncSession, limit: int) -> list[UUID]:
    collected: list[UUID] = []
    cursor: str | None = None
    # Ограничение на число итераций: цикл по курсору, который перестал
    # сдвигаться, иначе висел бы вечно.
    for _ in range(100):
        page = await CRUD.list_page(Widget, session, page=PageParams(cursor=cursor, limit=limit))
        collected.extend(widget.id for widget in page.items)
        cursor = page.next_cursor
        if cursor is None:
            return collected
    raise AssertionError("pagination did not terminate")


async def test_single_page_has_no_cursor(session: AsyncSession) -> None:
    await _fill(session, [BASE_MOMENT + timedelta(seconds=i) for i in range(3)])

    page = await CRUD.list_page(Widget, session, page=PageParams(limit=10))

    assert len(page.items) == 3
    assert page.next_cursor is None


async def test_walk_covers_every_row_once(session: AsyncSession) -> None:
    widgets = await _fill(session, [BASE_MOMENT + timedelta(seconds=i) for i in range(7)])

    collected = await _walk(session, limit=2)

    assert collected == _expected_order(widgets)


async def test_walk_survives_identical_timestamps(session: AsyncSession) -> None:
    """Ради этого случая id и входит в ключ: одной метки времени мало."""
    twin = BASE_MOMENT
    widgets = await _fill(session, [twin] * 5 + [twin + timedelta(seconds=1)] * 2)

    collected = await _walk(session, limit=2)

    assert len(collected) == len(set(collected)), "keyset returned duplicates"
    assert collected == _expected_order(widgets)


async def test_page_size_is_respected(session: AsyncSession) -> None:
    await _fill(session, [BASE_MOMENT + timedelta(seconds=i) for i in range(5)])

    page = await CRUD.list_page(Widget, session, page=PageParams(limit=2))

    assert len(page.items) == 2
    assert page.next_cursor is not None


async def test_where_filters_before_paging(session: AsyncSession) -> None:
    widgets = await _fill(session, [BASE_MOMENT + timedelta(seconds=i) for i in range(4)])
    widgets[0].deleted_at = BASE_MOMENT
    await session.flush()

    page = await CRUD.list_page(
        Widget, session, page=PageParams(limit=10), where=[Widget.deleted_at.is_(None)]
    )

    assert {widget.id for widget in page.items} == {w.id for w in widgets[1:]}


async def test_cursor_from_another_page_size_still_works(session: AsyncSession) -> None:
    widgets = await _fill(session, [BASE_MOMENT + timedelta(seconds=i) for i in range(6)])
    expected = _expected_order(widgets)

    first = await CRUD.list_page(Widget, session, page=PageParams(limit=4))
    second = await CRUD.list_page(
        Widget, session, page=PageParams(cursor=first.next_cursor, limit=10)
    )

    assert [widget.id for widget in first.items] == expected[:4]
    assert [widget.id for widget in second.items] == expected[4:]


async def test_model_without_created_at_fails_loudly(session: AsyncSession) -> None:
    """Без created_at keyset невозможен: это ошибка разработчика, не клиента."""
    await CRUD.create(Blob, BlobCreate(payload="data"), session)

    with pytest.raises(TypeError, match="created_at"):
        await CRUD.list_page(Blob, session, page=PageParams())
