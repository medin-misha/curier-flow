"""Доставка контактов курьера в транспорт и атомарность событий профиля."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.events.models import OutboxMessage
from app.modules.courier_module.events import CourierProfileChanged as OwnerProfileChanged
from app.modules.courier_module.models import Courier
from app.modules.courier_module.schemas.requests import CourierPatch
from app.modules.courier_module.services.couriers import delete_courier, patch_courier
from app.modules.transport_module.events import CourierDeleted, CourierProfileChanged
from app.modules.transport_module.models import TransportCourierProfile
from app.modules.transport_module.subscribers import sync_courier_profile


async def test_contact_projection_replay_order_and_deletion(session: AsyncSession) -> None:
    """Повтор и доставка не по порядку не возвращают старые или удалённые контакты."""
    courier_id = uuid4()
    now = datetime.now(tz=UTC)
    original = OwnerProfileChanged(
        courier_id=courier_id,
        full_name="Old Name",
        phone="+420777111222",
        changed_at=now,
    )
    event = CourierProfileChanged.model_validate(original.model_dump(mode="json"))
    updated = event.model_copy(
        update={
            "full_name": "New Name",
            "phone": "+420777333444",
            "changed_at": now + timedelta(seconds=1),
        }
    )
    await sync_courier_profile(updated, session)
    await sync_courier_profile(event, session)
    await sync_courier_profile(updated, session)
    profile = await session.get(TransportCourierProfile, courier_id)
    assert profile is not None
    assert (profile.full_name, profile.phone) == (updated.full_name, updated.phone)
    deleted = CourierDeleted(courier_id=courier_id, changed_at=now + timedelta(seconds=2))
    await sync_courier_profile(deleted, session)
    await sync_courier_profile(event, session)
    await sync_courier_profile(deleted, session)
    await sync_courier_profile(
        updated.model_copy(update={"changed_at": now + timedelta(days=1)}), session
    )
    await session.refresh(profile)
    assert profile.is_deleted
    assert profile.full_name is None
    assert profile.phone is None

    unseen_id = uuid4()
    await sync_courier_profile(deleted.model_copy(update={"courier_id": unseen_id}), session)
    await sync_courier_profile(event.model_copy(update={"courier_id": unseen_id}), session)
    unseen = await session.get(TransportCourierProfile, unseen_id)
    assert unseen is not None and unseen.is_deleted


async def test_profile_change_and_delete_emit_transactional_snapshots(
    session: AsyncSession,
) -> None:
    """PATCH и DELETE публикуют полные контакты только при успешной записи."""
    courier = Courier(
        full_name="Original Name",
        email=f"{uuid4()}@example.com",
        phone="+420777123456",
        date_of_birth=datetime(1990, 1, 1, tzinfo=UTC).date(),
        consent_to_processing=False,
    )
    session.add(courier)
    await session.flush()
    await patch_courier(courier.id, CourierPatch(full_name="Updated Name"), session=session)
    await session.flush()
    rows = list(
        (
            await session.scalars(
                select(OutboxMessage).where(OutboxMessage.topic == "courier.profile_changed")
            )
        ).all()
    )
    assert len(rows) == 1
    snapshot = CourierProfileChanged.model_validate(rows[0].payload)
    assert (snapshot.full_name, snapshot.phone) == ("Updated Name", "+420777123456")
    await patch_courier(courier.id, CourierPatch(full_name="Updated Name"), session=session)
    await session.flush()
    assert len(list((await session.scalars(select(OutboxMessage))).all())) == 1

    transaction = await session.begin_nested()
    await patch_courier(courier.id, CourierPatch(phone="+420777654321"), session=session)
    await session.flush()
    await transaction.rollback()
    await session.refresh(courier)
    assert courier.phone == "+420777123456"
    assert len(list((await session.scalars(select(OutboxMessage))).all())) == 1
    await delete_courier(courier.id, session=session)
    await session.flush()
    deletion = (
        await session.scalars(select(OutboxMessage).where(OutboxMessage.topic == "courier.deleted"))
    ).one()
    deleted = CourierDeleted.model_validate(deletion.payload)
    assert deleted.courier_id == snapshot.courier_id
    assert deleted.changed_at > snapshot.changed_at
