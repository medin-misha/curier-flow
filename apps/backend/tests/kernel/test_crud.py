"""Типовые операции: создание, чтение, белый список патча, удаление."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, NotFound
from tests.models import Blob, Widget
from tests.schemas import BlobCreate, WidgetCreate, WidgetPatch


async def test_create_fills_generated_columns(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="first"), session)

    assert widget.id is not None
    assert widget.created_at is not None
    assert widget.updated_at is not None
    assert widget.deleted_at is None


async def test_generated_id_is_stdlib_uuid(session: AsyncSession) -> None:
    """uuid_utils.uuid7 возвращает свой тип, несовместимый с SQLAlchemy и Pydantic."""
    widget = await CRUD.create(Widget, WidgetCreate(name="typed"), session)

    assert isinstance(widget.id, uuid.UUID)
    assert type(widget.id) is uuid.UUID
    assert widget.id.version == 7


async def test_ids_grow_monotonically(session: AsyncSession) -> None:
    """UUIDv7 упорядочен по времени — на этом держится локальность индекса."""
    first = await CRUD.create(Widget, WidgetCreate(name="a"), session)
    second = await CRUD.create(Widget, WidgetCreate(name="b"), session)

    assert first.id < second.id


async def test_overrides_win_over_client_data(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="client"), session, name="server")

    assert widget.name == "server"


async def test_get_returns_none_for_missing_row(session: AsyncSession) -> None:
    assert await CRUD.get(Widget, uuid.uuid4(), session) is None


async def test_get_or_404_names_the_model(session: AsyncSession) -> None:
    missing = uuid.uuid4()

    with pytest.raises(NotFound) as raised:
        await CRUD.get_or_404(Widget, missing, session)

    assert "Widget" in raised.value.detail
    assert raised.value.status == 404
    assert raised.value.extra == {"resource": "Widget", "pk": str(missing)}


async def test_update_applies_whitelisted_fields(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="old", quantity=1), session)

    await CRUD.update(widget, WidgetPatch(name="new"), session)

    assert widget.name == "new"


async def test_update_ignores_fields_client_did_not_send(session: AsyncSession) -> None:
    """exclude_unset: PATCH без quantity не должен обнулять quantity."""
    widget = await CRUD.create(Widget, WidgetCreate(name="old", quantity=5), session)

    await CRUD.update(widget, WidgetPatch(name="new"), session)

    assert widget.quantity == 5


async def test_update_accepts_explicit_none(session: AsyncSession) -> None:
    """Явный null отличается от «поле не передали»."""
    widget = await CRUD.create(Widget, WidgetCreate(name="old"), session, deleted_at=_hours_ago(1))

    await CRUD.update(
        widget, WidgetPatch(deleted_at=None), session, allowed=frozenset({"deleted_at"})
    )

    assert widget.deleted_at is None


async def test_update_rejects_field_outside_whitelist(session: AsyncSession) -> None:
    """Запрещённое поле — ошибка, а не молчаливая фильтрация."""
    widget = await CRUD.create(Widget, WidgetCreate(name="old"), session, owner="system")

    with pytest.raises(Conflict) as raised:
        await CRUD.update(widget, WidgetPatch(name="new", owner="hacker"), session)

    assert raised.value.status == 409
    assert widget.owner == "system"
    assert widget.name == "old"


async def test_conflict_lists_forbidden_fields_in_order(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="old"), session)

    with pytest.raises(Conflict) as raised:
        await CRUD.update(
            widget,
            WidgetPatch(owner="hacker", name="new"),
            session,
            allowed=frozenset(),
        )

    assert raised.value.detail == "Fields are not patchable: name, owner"
    assert raised.value.extra == {"fields": ["name", "owner"]}


async def test_empty_whitelist_forbids_any_patch(session: AsyncSession) -> None:
    """Пустой __patchable__ по умолчанию значит «патчить нечего»."""
    blob = await CRUD.create(Blob, BlobCreate(payload="data"), session)

    with pytest.raises(Conflict):
        await CRUD.update(blob, BlobCreate(payload="other"), session)


async def test_explicit_allowed_overrides_model_whitelist(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="old"), session)

    await CRUD.update(widget, WidgetPatch(owner="operator"), session, allowed=frozenset({"owner"}))

    assert widget.owner == "operator"


async def test_updated_at_moves_forward(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="old"), session, updated_at=_hours_ago(1))
    before = widget.updated_at

    await CRUD.update(widget, WidgetPatch(name="new"), session)

    assert widget.updated_at > before


async def test_delete_removes_row(session: AsyncSession) -> None:
    widget = await CRUD.create(Widget, WidgetCreate(name="doomed"), session)
    widget_id = widget.id

    await CRUD.delete(widget, session)

    assert await CRUD.get(Widget, widget_id, session) is None


def _hours_ago(hours: int) -> datetime:
    return datetime.now(tz=UTC) - timedelta(hours=hours)
