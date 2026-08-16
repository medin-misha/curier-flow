"""Границы транзакции: коммит, откат, чтение после коммита."""

from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy import select

from app.kernel.db import session as session_module
from app.kernel.db.crud import CRUD
from app.kernel.db.session import get_ro_session, get_uow
from tests.models import Widget
from tests.schemas import WidgetCreate

uow = asynccontextmanager(get_uow)
ro_session = asynccontextmanager(get_ro_session)


async def _name_of(widget_id: UUID) -> str | None:
    """Прочитать имя отдельной сессией: то, что реально лежит в базе."""
    async with session_module.session_factory() as fresh:
        name: str | None = await fresh.scalar(select(Widget.name).where(Widget.id == widget_id))
    return name


@pytest.mark.usefixtures("clean_db")
async def test_uow_commits_on_normal_exit() -> None:
    async with uow() as session:
        widget = await CRUD.create(Widget, WidgetCreate(name="committed"), session)
        widget_id = widget.id

    assert await _name_of(widget_id) == "committed"


@pytest.mark.usefixtures("clean_db")
async def test_uow_rolls_back_on_error() -> None:
    widget_id: UUID | None = None

    with pytest.raises(RuntimeError, match="boom"):
        async with uow() as session:
            widget = await CRUD.create(Widget, WidgetCreate(name="doomed"), session)
            widget_id = widget.id
            raise RuntimeError("boom")

    assert widget_id is not None
    assert await _name_of(widget_id) is None


@pytest.mark.usefixtures("clean_db")
async def test_attributes_readable_after_commit() -> None:
    """expire_on_commit=False: сериализация ответа не должна лезть в БД."""
    async with uow() as session:
        widget = await CRUD.create(Widget, WidgetCreate(name="alive", quantity=7), session)

    assert widget.name == "alive"
    assert widget.quantity == 7
    assert widget.created_at is not None


def test_session_factory_keeps_objects_alive() -> None:
    assert session_module.session_factory.kw["expire_on_commit"] is False


@pytest.mark.usefixtures("clean_db")
async def test_ro_session_does_not_persist_changes() -> None:
    async with uow() as session:
        widget = await CRUD.create(Widget, WidgetCreate(name="original"), session)
        widget_id = widget.id

    async with ro_session() as session:
        loaded = await CRUD.get_or_404(Widget, widget_id, session)
        loaded.name = "sneaky"
        await session.flush()

    assert await _name_of(widget_id) == "original"


@pytest.mark.usefixtures("clean_db")
async def test_ro_session_reads_committed_rows() -> None:
    async with uow() as session:
        widget = await CRUD.create(Widget, WidgetCreate(name="visible"), session)
        widget_id = widget.id

    async with ro_session() as session:
        assert (await CRUD.get_or_404(Widget, widget_id, session)).name == "visible"
