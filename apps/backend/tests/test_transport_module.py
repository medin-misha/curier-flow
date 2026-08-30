"""Транспорт, комплектация, аренда и защита подписанного договора."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text, update

from app.kernel.db import session as session_module
from app.kernel.idempotency import is_idempotent
from app.kernel.security.authentication import is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.courier_module.models import Courier
from app.modules.courier_module.module import courier_module
from app.modules.storage.module import storage_module
from app.modules.transport_module.models import CourierTransport, Transport, TransportComponent
from app.modules.transport_module.module import transport_module
from app.platform.files import File, FileStatus
from tests.asgi import app_client, build_app

ADMIN_ID: Final = UUID(int=501)
PROBLEM_JSON: Final = "application/problem+json"
BASE_TRANSPORT: Final[dict[str, Any]] = {
    "type": " E-BIKE ",
    "model": " City Runner ",
    "serial_number": " cf-001 ",
    "color": " Black ",
    "deposit_required": False,
    "deposit_amount": None,
    "rental_price": "1250.00",
}


async def _clear_transport_data() -> None:
    """Очистить trigger-protected таблицы в безопасном test-only порядке."""
    async with session_module.session_factory() as session, session.begin():
        await session.execute(
            text(
                "TRUNCATE TABLE courier_transports, transport_components, transports "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.execute(delete(Courier))
        await session.execute(delete(File))


@pytest.fixture
async def transport_database(clean_db: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Настоящие транзакции и уборка строк, защищённых DELETE-trigger."""
    await _clear_transport_data()
    try:
        yield
    finally:
        await _clear_transport_data()


@pytest.fixture
async def client(transport_database: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    """Клиент transport, storage DELETE и courier DELETE с Admin JWT."""
    async with app_client(
        [transport_module, storage_module, courier_module],
        raise_app_exceptions=False,
    ) as http:
        access = issue_tokens(
            ADMIN_ID,
            settings=jwt_settings,
            claims={"kind": "admin"},
        ).access_token
        http.headers["authorization"] = f"Bearer {access}"
        yield http


def idempotency_headers(key: str | None = None) -> dict[str, str]:
    """Выдать уникальный ключ для command endpoint."""
    return {"Idempotency-Key": key or uuid4().hex}


async def create_transport(
    client: AsyncClient,
    *,
    serial_number: str = "cf-001",
    key: str | None = None,
) -> dict[str, Any]:
    """Создать транспорт через публичный HTTP-контракт."""
    response = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "serial_number": serial_number},
        headers=idempotency_headers(key),
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    payload: dict[str, Any] = response.json()
    return payload


async def create_courier(*, suffix: str | None = None) -> UUID:
    """Создать минимальный Courier напрямую, не импортируя его в transport code."""
    marker = suffix or uuid4().hex[:10]
    courier_id = uuid4()
    async with session_module.session_factory() as session, session.begin():
        session.add(
            Courier(
                id=courier_id,
                full_name=f"Courier {marker}",
                email=f"{marker}@example.com",
                phone=f"+4207{int(courier_id.int % 100_000_000):08d}",
                date_of_birth=datetime(1990, 1, 1, tzinfo=UTC).date(),
                consent_to_processing=False,
                consent_at=None,
            )
        )
    return courier_id


async def create_file(status: FileStatus = FileStatus.READY) -> UUID:
    """Создать File нужного lifecycle-состояния напрямую."""
    file_id = uuid4()
    async with session_module.session_factory() as session, session.begin():
        session.add(
            File(
                id=file_id,
                bucket="contracts",
                key=str(file_id),
                original_name="contract.pdf",
                content_type="application/pdf",
                size=128,
                etag="etag" if status is FileStatus.READY else None,
                status=status,
            )
        )
    return file_id


async def create_rental(
    client: AsyncClient,
    transport_id: str,
    courier_id: UUID,
    *,
    started_at: datetime,
    ended_at: datetime | None = None,
    file_id: UUID | None = None,
) -> Any:
    """Создать аренду с отдельным идемпотентным ключом."""
    body: dict[str, Any] = {
        "courier_id": str(courier_id),
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat() if ended_at is not None else None,
        "file_id": str(file_id) if file_id is not None else None,
    }
    return await client.post(
        f"/transport/{transport_id}/rentals",
        json=body,
        headers=idempotency_headers(),
    )


async def test_every_transport_endpoint_requires_admin_jwt(client: AsyncClient) -> None:
    authorization = client.headers.pop("authorization")
    transport_id = uuid4()
    child_id = uuid4()
    requests = (
        ("POST", "/transport"),
        ("GET", "/transport"),
        ("GET", f"/transport/{transport_id}"),
        ("PATCH", f"/transport/{transport_id}"),
        ("DELETE", f"/transport/{transport_id}"),
        ("POST", f"/transport/{transport_id}/components"),
        ("GET", f"/transport/{transport_id}/components"),
        ("GET", f"/transport/{transport_id}/components/{child_id}"),
        ("PATCH", f"/transport/{transport_id}/components/{child_id}"),
        ("DELETE", f"/transport/{transport_id}/components/{child_id}"),
        ("POST", f"/transport/{transport_id}/rentals"),
        ("GET", f"/transport/{transport_id}/rentals"),
        ("GET", f"/transport/{transport_id}/rentals/{child_id}"),
        ("POST", f"/transport/{transport_id}/rentals/{child_id}/close"),
        ("POST", f"/transport/{transport_id}/rentals/{child_id}/contract"),
    )
    try:
        for method, path in requests:
            response = await client.request(method, path, json={})
            assert response.status_code == HTTPStatus.UNAUTHORIZED, (method, path, response.text)
            assert response.headers["content-type"] == PROBLEM_JSON
            assert response.json()["reason"] == "missing-token"
    finally:
        client.headers["authorization"] = authorization


async def test_transport_crud_normalization_decimal_and_validation(client: AsyncClient) -> None:
    key = "transport-replay"
    created_response = await client.post(
        "/transport",
        json=BASE_TRANSPORT,
        headers=idempotency_headers(key),
    )
    replay = await client.post(
        "/transport",
        json=BASE_TRANSPORT,
        headers=idempotency_headers(key),
    )
    created = created_response.json()

    assert created_response.status_code == HTTPStatus.CREATED
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.content == created_response.content
    assert (created["type"], created["model"], created["serial_number"], created["color"]) == (
        "e-bike",
        "City Runner",
        "CF-001",
        "Black",
    )
    assert created["rental_price"] == "1250.00"
    assert created["deposit_amount"] is None
    assert created["components"] == []
    assert created["active_rental"] is None

    unknown = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "owner_id": str(uuid4())},
        headers=idempotency_headers(),
    )
    bad_scale = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "serial_number": "scale", "rental_price": "1.234"},
        headers=idempotency_headers(),
    )
    explicit_null = await client.patch(
        f"/transport/{created['id']}",
        json={"color": None},
    )
    missing_deposit = await client.patch(
        f"/transport/{created['id']}",
        json={"deposit_required": True},
    )
    patched = await client.patch(
        f"/transport/{created['id']}",
        json={"deposit_required": True, "deposit_amount": "500.00"},
    )
    cleared = await client.patch(
        f"/transport/{created['id']}",
        json={"deposit_required": False},
    )
    duplicate = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "type": "scooter"},
        headers=idempotency_headers(),
    )

    assert unknown.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_scale.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert explicit_null.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert missing_deposit.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert patched.json()["deposit_amount"] == "500.00"
    assert cleared.json()["deposit_amount"] is None
    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.json()["reason"] == "duplicate-serial-number"

    removed = await client.delete(f"/transport/{created['id']}")
    assert removed.status_code == HTTPStatus.NO_CONTENT
    assert (await client.get(f"/transport/{created['id']}")).status_code == HTTPStatus.NOT_FOUND


async def test_transport_keyset_filters_and_identical_timestamps(client: AsyncClient) -> None:
    transports = [
        await create_transport(client, serial_number=f"page-{number}") for number in range(3)
    ]
    moment = datetime.now(tz=UTC) - timedelta(minutes=1)
    async with session_module.session_factory() as session, session.begin():
        await session.execute(update(Transport).values(created_at=moment))

    first = (await client.get("/transport", params={"limit": 2, "type": " E-BIKE "})).json()
    rest = (
        await client.get(
            "/transport",
            params={"cursor": first["next_cursor"], "type": "e-bike"},
        )
    ).json()
    exact = (
        await client.get(
            "/transport",
            params={"serial_number": transports[0]["serial_number"].lower()},
        )
    ).json()

    ids = [item["id"] for item in first["items"] + rest["items"]]
    assert len(ids) == len(set(ids)) == 3
    assert rest["next_cursor"] is None
    assert [item["id"] for item in exact["items"]] == [transports[0]["id"]]


async def test_component_crud_totals_pagination_and_parent_isolation(client: AsyncClient) -> None:
    first = await create_transport(client, serial_number="component-1")
    second = await create_transport(client, serial_number="component-2")
    components = []
    for number in range(3):
        response = await client.post(
            f"/transport/{first['id']}/components",
            json={"name": f" Helmet {number} ", "unit_price": "25.50", "quantity": 2},
            headers=idempotency_headers(),
        )
        assert response.status_code == HTTPStatus.CREATED, response.text
        components.append(response.json())
    assert components[0]["unit_price"] == "25.50"
    assert components[0]["total_price"] == "51.00"

    duplicate = await client.post(
        f"/transport/{first['id']}/components",
        json={"name": "Helmet 0", "unit_price": "1.00", "quantity": 1},
        headers=idempotency_headers(),
    )
    wrong_parent = await client.get(f"/transport/{second['id']}/components/{components[0]['id']}")
    explicit_null = await client.patch(
        f"/transport/{first['id']}/components/{components[0]['id']}",
        json={"quantity": None},
    )
    patched = await client.patch(
        f"/transport/{first['id']}/components/{components[0]['id']}",
        json={"quantity": 3},
    )

    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.json()["reason"] == "duplicate-component"
    assert wrong_parent.status_code == HTTPStatus.NOT_FOUND
    assert explicit_null.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert patched.json()["total_price"] == "76.50"

    moment = datetime.now(tz=UTC) - timedelta(minutes=1)
    async with session_module.session_factory() as session, session.begin():
        await session.execute(
            update(TransportComponent)
            .where(TransportComponent.transport_id == UUID(first["id"]))
            .values(created_at=moment)
        )
    page = (await client.get(f"/transport/{first['id']}/components", params={"limit": 2})).json()
    rest = (
        await client.get(
            f"/transport/{first['id']}/components",
            params={"cursor": page["next_cursor"]},
        )
    ).json()
    assert len({item["id"] for item in page["items"] + rest["items"]}) == 3

    removed = await client.delete(f"/transport/{first['id']}/components/{components[0]['id']}")
    assert removed.status_code == HTTPStatus.NO_CONTENT


async def test_rental_history_overlap_close_filters_and_replay(client: AsyncClient) -> None:
    first_transport = await create_transport(client, serial_number="rental-1")
    second_transport = await create_transport(client, serial_number="rental-2")
    first_courier = await create_courier(suffix="rental-first")
    second_courier = await create_courier(suffix="rental-second")
    now = datetime.now(tz=UTC)
    started = now - timedelta(days=5)

    active_response = await create_rental(
        client,
        first_transport["id"],
        first_courier,
        started_at=started,
    )
    active = active_response.json()
    transport_overlap = await create_rental(
        client,
        first_transport["id"],
        second_courier,
        started_at=now - timedelta(days=4),
    )
    courier_overlap = await create_rental(
        client,
        second_transport["id"],
        first_courier,
        started_at=now - timedelta(days=4),
    )

    assert active_response.status_code == HTTPStatus.CREATED
    assert active["is_active"] is True
    assert transport_overlap.status_code == HTTPStatus.CONFLICT
    assert transport_overlap.json()["reason"] == "transport-rental-overlap"
    assert courier_overlap.status_code == HTTPStatus.CONFLICT
    assert courier_overlap.json()["reason"] == "courier-rental-overlap"

    close_key = "close-rental-replay"
    close_body = {"ended_at": (now - timedelta(days=3)).isoformat()}
    closed = await client.post(
        f"/transport/{first_transport['id']}/rentals/{active['id']}/close",
        json=close_body,
        headers=idempotency_headers(close_key),
    )
    replay = await client.post(
        f"/transport/{first_transport['id']}/rentals/{active['id']}/close",
        json=close_body,
        headers=idempotency_headers(close_key),
    )
    repeated = await client.post(
        f"/transport/{first_transport['id']}/rentals/{active['id']}/close",
        json=close_body,
        headers=idempotency_headers(),
    )
    adjacent = await create_rental(
        client,
        first_transport["id"],
        second_courier,
        started_at=now - timedelta(days=3),
        ended_at=now - timedelta(days=2),
    )

    assert closed.status_code == HTTPStatus.OK
    assert closed.json()["is_active"] is False
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert repeated.status_code == HTTPStatus.CONFLICT
    assert repeated.json()["reason"] == "rental-already-closed"
    assert adjacent.status_code == HTTPStatus.CREATED, adjacent.text

    available = (await client.get("/transport", params={"is_available": True})).json()["items"]
    by_current_courier = (
        await client.get("/transport", params={"courier_id": str(first_courier)})
    ).json()["items"]
    history = (await client.get(f"/transport/{first_transport['id']}/rentals")).json()["items"]
    assert first_transport["id"] in {item["id"] for item in available}
    assert by_current_courier == []
    assert len(history) == 2


async def test_concurrent_conflicting_rentals_have_one_winner(client: AsyncClient) -> None:
    transport = await create_transport(client, serial_number="race-transport")
    couriers = await asyncio.gather(create_courier(), create_courier())
    started = datetime.now(tz=UTC) - timedelta(hours=1)

    responses = await asyncio.gather(
        *(
            create_rental(client, transport["id"], courier_id, started_at=started)
            for courier_id in couriers
        )
    )

    assert sorted(response.status_code for response in responses) == [
        HTTPStatus.CREATED,
        HTTPStatus.CONFLICT,
    ]
    conflict = next(
        response for response in responses if response.status_code == HTTPStatus.CONFLICT
    )
    assert conflict.json()["reason"] == "transport-rental-overlap"
    async with session_module.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(CourierTransport))
    assert count == 1


async def test_contract_ready_immutability_reuse_and_delete_protection(client: AsyncClient) -> None:
    transport = await create_transport(client, serial_number="contract-1")
    second_transport = await create_transport(client, serial_number="contract-2")
    courier_id = await create_courier(suffix="contract-first")
    second_courier = await create_courier(suffix="contract-second")
    started = datetime.now(tz=UTC) - timedelta(days=1)
    rental = (await create_rental(client, transport["id"], courier_id, started_at=started)).json()
    second_rental = (
        await create_rental(client, second_transport["id"], second_courier, started_at=started)
    ).json()
    pending_file = await create_file(FileStatus.PENDING)
    ready_file = await create_file()
    replacement_file = await create_file()

    pending = await client.post(
        f"/transport/{transport['id']}/rentals/{rental['id']}/contract",
        json={"file_id": str(pending_file)},
        headers=idempotency_headers(),
    )
    attach_key = "attach-contract-replay"
    attached = await client.post(
        f"/transport/{transport['id']}/rentals/{rental['id']}/contract",
        json={"file_id": str(ready_file)},
        headers=idempotency_headers(attach_key),
    )
    replay = await client.post(
        f"/transport/{transport['id']}/rentals/{rental['id']}/contract",
        json={"file_id": str(ready_file)},
        headers=idempotency_headers(attach_key),
    )
    replacement = await client.post(
        f"/transport/{transport['id']}/rentals/{rental['id']}/contract",
        json={"file_id": str(replacement_file)},
        headers=idempotency_headers(),
    )
    reused = await client.post(
        f"/transport/{second_transport['id']}/rentals/{second_rental['id']}/contract",
        json={"file_id": str(ready_file)},
        headers=idempotency_headers(),
    )

    assert pending.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert pending.json()["reason"] == "file-not-ready"
    assert attached.status_code == HTTPStatus.OK
    assert attached.json()["file"]["id"] == str(ready_file)
    assert "bucket" not in attached.text
    assert "key" not in attached.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replacement.status_code == HTTPStatus.CONFLICT
    assert replacement.json()["reason"] == "contract-already-attached"
    assert reused.status_code == HTTPStatus.CONFLICT
    assert reused.json()["reason"] == "contract-file-in-use"

    file_delete = await client.delete(f"/files/{ready_file}")
    transport_delete = await client.delete(f"/transport/{transport['id']}")
    courier_delete = await client.delete(f"/courier/{courier_id}")

    assert file_delete.status_code == HTTPStatus.CONFLICT
    assert file_delete.json()["reason"] == "file-in-use"
    assert transport_delete.status_code == HTTPStatus.CONFLICT
    assert transport_delete.json()["reason"] == "signed-contract-protects-rental"
    assert courier_delete.status_code == HTTPStatus.CONFLICT
    assert courier_delete.json()["reason"] == "signed-contract-protects-rental"
    async with session_module.session_factory() as session:
        file = await session.get(File, ready_file)
        courier = await session.get(Courier, courier_id)
        stored_rental = await session.get(CourierTransport, UUID(rental["id"]))
    assert file is not None and file.status is FileStatus.READY
    assert courier is not None
    assert stored_rental is not None and stored_rental.file_id == ready_file


async def test_unsigned_history_cascades_with_transport_and_courier(client: AsyncClient) -> None:
    first_transport = await create_transport(client, serial_number="cascade-transport")
    first_courier = await create_courier(suffix="cascade-first")
    first_rental = (
        await create_rental(
            client,
            first_transport["id"],
            first_courier,
            started_at=datetime.now(tz=UTC) - timedelta(days=1),
        )
    ).json()

    removed_transport = await client.delete(f"/transport/{first_transport['id']}")
    assert removed_transport.status_code == HTTPStatus.NO_CONTENT

    second_transport = await create_transport(client, serial_number="cascade-courier")
    second_courier = await create_courier(suffix="cascade-second")
    second_rental = (
        await create_rental(
            client,
            second_transport["id"],
            second_courier,
            started_at=datetime.now(tz=UTC) - timedelta(days=1),
        )
    ).json()
    removed_courier = await client.delete(f"/courier/{second_courier}")

    assert removed_courier.status_code == HTTPStatus.NO_CONTENT
    async with session_module.session_factory() as session:
        assert await session.get(CourierTransport, UUID(first_rental["id"])) is None
        assert await session.get(CourierTransport, UUID(second_rental["id"])) is None
        assert await session.get(Transport, UUID(second_transport["id"])) is not None


async def test_postgresql_constraints_triggers_and_indexes(transport_database: None) -> None:  # noqa: ARG001
    async with session_module.session_factory() as session:
        extension = await session.scalar(
            text("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
        )
        constraint_rows = await session.execute(
            text(
                "SELECT conname, contype::text AS contype FROM pg_constraint "
                "WHERE conrelid = 'courier_transports'::regclass"
            )
        )
        constraints = {str(row.conname): str(row.contype) for row in constraint_rows}
        triggers = set(
            (
                await session.scalars(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE NOT tgisinternal AND tgrelid IN "
                        "('courier_transports'::regclass, 'files'::regclass)"
                    )
                )
            ).all()
        )
        index_rows = await session.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename IN "
                "('transports', 'transport_components', 'courier_transports')"
            )
        )
        indexes = {str(row.indexname): str(row.indexdef) for row in index_rows}

    assert extension == "btree_gist"
    assert constraints["excl_courier_transports_transport_period"] == "x"
    assert constraints["excl_courier_transports_courier_period"] == "x"
    assert {
        "transport_require_ready_contract_file",
        "transport_protect_signed_rental",
        "transport_protect_contract_file",
    } <= triggers
    assert "created_at DESC, id DESC" in indexes["ix_transports_keyset"]
    assert (
        "transport_id, created_at DESC, id DESC"
        in indexes["ix_transport_components_transport_keyset"]
    )
    assert (
        "transport_id, created_at DESC, id DESC"
        in indexes["ix_courier_transports_transport_keyset"]
    )


def test_manifest_route_markers_and_openapi_contract() -> None:
    app = build_app([transport_module])
    assert transport_module.url_prefix == "/transport"
    assert transport_module.models == "app.modules.transport_module.models"
    assert transport_module.router is not None

    auth = {}
    idempotency = set()
    for route in transport_module.router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            key = (method, f"{transport_module.url_prefix}{route.path}")
            auth[key] = is_authenticated(route.endpoint)
            if is_idempotent(route.endpoint):
                idempotency.add(key)

    assert len(auth) == 15
    assert all(auth.values())
    assert idempotency == {
        ("POST", "/transport"),
        ("POST", "/transport/{transport_id}/components"),
        ("POST", "/transport/{transport_id}/rentals"),
        ("POST", "/transport/{transport_id}/rentals/{rental_id}/close"),
        ("POST", "/transport/{transport_id}/rentals/{rental_id}/contract"),
    }
    assert "/transport/{transport_id}/rentals/{rental_id}/contract" in app.openapi()["paths"]
