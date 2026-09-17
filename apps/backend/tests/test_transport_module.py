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
from sqlalchemy.exc import IntegrityError

from app.kernel.db import session as session_module
from app.kernel.idempotency import IdempotencyKey, is_idempotent
from app.kernel.security.authentication import is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.courier_module.models import (
    Courier,
    CourierDocument,
    CourierPlatformAccount,
    DeliveryPlatform,
    DocumentPurpose,
    DocumentType,
    PlatformAccountStatus,
)
from app.modules.courier_module.module import courier_module
from app.modules.storage.module import storage_module
from app.modules.transport_module.models import (
    CourierTransport,
    Transport,
    TransportComponent,
)
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
    payment_type: str = "monthly",
) -> Any:
    """Создать аренду с отдельным идемпотентным ключом."""
    body: dict[str, Any] = {
        "courier_id": str(courier_id),
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat() if ended_at is not None else None,
        "file_id": str(file_id) if file_id is not None else None,
        "payment_type": payment_type,
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
        ("PATCH", f"/transport/{transport_id}/rentals/{child_id}"),
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
    assert created["ordinal_number"] is None
    assert created["comment"] is None
    assert created["debt_amount"] == "0.00"
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
    negative_debt = await client.patch(
        f"/transport/{created['id']}",
        json={"debt_amount": "-0.01"},
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
        json={
            "deposit_required": True,
            "deposit_amount": "500.00",
            "comment": " Needs service ",
            "debt_amount": "350.50",
        },
    )
    cleared_comment = await client.patch(
        f"/transport/{created['id']}",
        json={"comment": None},
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
    assert negative_debt.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert explicit_null.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert missing_deposit.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert patched.json()["deposit_amount"] == "500.00"
    assert patched.json()["comment"] == "Needs service"
    assert patched.json()["debt_amount"] == "350.50"
    assert cleared_comment.json()["comment"] is None
    assert cleared.json()["deposit_amount"] is None
    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.json()["reason"] == "duplicate-serial-number"

    removed = await client.delete(f"/transport/{created['id']}")
    assert removed.status_code == HTTPStatus.NO_CONTENT
    assert (await client.get(f"/transport/{created['id']}")).status_code == HTTPStatus.NOT_FOUND


async def test_transport_ordinal_number_create_patch_clear_and_list(client: AsyncClient) -> None:
    created_response = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "ordinal_number": 17},
        headers=idempotency_headers(),
    )
    assert created_response.status_code == HTTPStatus.CREATED
    created = created_response.json()
    assert created["ordinal_number"] == 17
    url = f"/transport/{created['id']}"

    duplicate = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "serial_number": "other-number", "ordinal_number": 17},
        headers=idempotency_headers(),
    )
    assert duplicate.status_code == HTTPStatus.CREATED
    assert (await client.get("/transport")).json()["items"][0]["ordinal_number"] == 17

    preserved = await client.patch(url, json={"color": "Blue"})
    assert preserved.json()["ordinal_number"] == 17
    changed = await client.patch(url, json={"ordinal_number": 2_147_483_647})
    assert changed.status_code == HTTPStatus.OK
    assert changed.json()["ordinal_number"] == 2_147_483_647
    cleared = await client.patch(url, json={"ordinal_number": None})
    assert cleared.status_code == HTTPStatus.OK
    assert cleared.json()["ordinal_number"] is None
    assert (await client.get(url)).json()["ordinal_number"] is None

    explicit_null = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "serial_number": "null-number", "ordinal_number": None},
        headers=idempotency_headers(),
    )
    assert explicit_null.status_code == HTTPStatus.CREATED
    assert explicit_null.json()["ordinal_number"] is None


@pytest.mark.parametrize("value", [0, -1, 1.5, 1.0, True, "1", 2_147_483_648])
async def test_transport_ordinal_number_rejects_invalid_values(
    client: AsyncClient, value: Any
) -> None:
    transport = await create_transport(client)
    created = await client.post(
        "/transport",
        json={**BASE_TRANSPORT, "serial_number": "invalid-number", "ordinal_number": value},
        headers=idempotency_headers(),
    )
    patched = await client.patch(f"/transport/{transport['id']}", json={"ordinal_number": value})
    assert created.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert patched.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


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
    assert "comment" not in first["items"][0]
    assert "debt_amount" not in first["items"][0]


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


@pytest.mark.parametrize("payment_type", ["monthly", "weekly", "weekly_in_arrears"])
async def test_rental_payment_type_create_and_read(client: AsyncClient, payment_type: str) -> None:
    transport = await create_transport(client)
    courier_id = await create_courier()
    response = await create_rental(
        client,
        transport["id"],
        courier_id,
        started_at=datetime.now(tz=UTC) - timedelta(days=1),
        payment_type=payment_type,
    )
    assert response.status_code == HTTPStatus.CREATED
    rental = response.json()
    assert rental["payment_type"] == payment_type
    base_url = f"/transport/{transport['id']}"
    assert (await client.get(base_url)).json()["active_rental"]["payment_type"] == payment_type
    assert (await client.get(f"{base_url}/rentals")).json()["items"][0][
        "payment_type"
    ] == payment_type
    assert (await client.get(f"{base_url}/rentals/{rental['id']}")).json()[
        "payment_type"
    ] == payment_type


async def test_rental_creation_requires_valid_payment_type(client: AsyncClient) -> None:
    transport = await create_transport(client)
    body = {
        "courier_id": str(await create_courier()),
        "started_at": (datetime.now(tz=UTC) - timedelta(days=1)).isoformat(),
    }
    for payment_fields in ({}, {"payment_type": None}, {"payment_type": "daily"}):
        response = await client.post(
            f"/transport/{transport['id']}/rentals",
            json={**body, **payment_fields},
            headers=idempotency_headers(),
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, response.text


@pytest.mark.parametrize("closed", [False, True])
async def test_legacy_rental_payment_patch_preserves_period_and_contract(
    client: AsyncClient, closed: bool
) -> None:
    transport = await create_transport(client)
    other_transport = await create_transport(client, serial_number="other-parent")
    courier_id = await create_courier()
    file_id = await create_file()
    rental_id = uuid4()
    started_at = datetime.now(tz=UTC) - timedelta(days=3)
    ended_at = started_at + timedelta(days=1) if closed else None
    async with session_module.session_factory() as session, session.begin():
        session.add(
            CourierTransport(
                id=rental_id,
                transport_id=UUID(transport["id"]),
                courier_id=courier_id,
                started_at=started_at,
                ended_at=ended_at,
                file_id=file_id,
            )
        )

    url = f"/transport/{transport['id']}/rentals/{rental_id}"
    before = (await client.get(url)).json()
    assert before["payment_type"] is None
    legacy_history = (await client.get(f"/transport/{transport['id']}/rentals")).json()
    assert legacy_history["items"][0]["payment_type"] is None
    detail = (await client.get(f"/transport/{transport['id']}")).json()
    if not closed:
        assert detail["active_rental"]["payment_type"] is None

    for invalid in (
        {},
        {"payment_type": None},
        {"payment_type": "daily"},
        {"payment_type": "monthly", "courier_id": str(courier_id)},
        {"payment_type": "monthly", "file_id": None},
        {"payment_type": "monthly", "started_at": started_at.isoformat()},
        {"payment_type": "monthly", "ended_at": None},
    ):
        response = await client.patch(url, json=invalid)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, response.text

    wrong_parent = await client.patch(
        f"/transport/{other_transport['id']}/rentals/{rental_id}",
        json={"payment_type": "monthly"},
    )
    missing_rental = await client.patch(
        f"/transport/{transport['id']}/rentals/{uuid4()}",
        json={"payment_type": "monthly"},
    )
    assert wrong_parent.status_code == HTTPStatus.NOT_FOUND
    assert missing_rental.status_code == HTTPStatus.NOT_FOUND
    for payment_type in ("monthly", "weekly", "weekly_in_arrears"):
        response = await client.patch(url, json={"payment_type": payment_type})
        assert response.status_code == HTTPStatus.OK, response.text
        after = response.json()
        assert after["payment_type"] == payment_type
        for field in ("courier_id", "transport_id", "file_id", "started_at", "ended_at"):
            assert after[field] == before[field]
        assert (await client.get(url)).json()["payment_type"] == payment_type

    assert (
        await client.patch(url, json={"payment_type": None})
    ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_transport_payment_and_ordinal_constraints_enforced_in_database(
    client: AsyncClient,
) -> None:
    transport = await create_transport(client)
    rental_response = await create_rental(
        client,
        transport["id"],
        await create_courier(),
        started_at=datetime.now(tz=UTC) - timedelta(days=1),
    )
    assert rental_response.status_code == HTTPStatus.CREATED
    rental_id = rental_response.json()["id"]
    for statement, pk in (
        ("UPDATE transports SET ordinal_number = 0 WHERE id = :id", transport["id"]),
        ("UPDATE transports SET ordinal_number = -1 WHERE id = :id", transport["id"]),
        ("UPDATE courier_transports SET payment_type = 'daily' WHERE id = :id", rental_id),
    ):
        with pytest.raises(IntegrityError):
            async with session_module.session_factory() as session, session.begin():
                await session.execute(text(statement), {"id": UUID(pk)})


async def test_close_rental_accepts_future_end_and_closes_immediately(
    client: AsyncClient,
) -> None:
    transport = await create_transport(client, serial_number="future-close")
    courier_id = await create_courier(suffix="future-close")
    started = datetime.now(tz=UTC) - timedelta(days=1)
    rental = (await create_rental(client, transport["id"], courier_id, started_at=started)).json()
    close_url = f"/transport/{transport['id']}/rentals/{rental['id']}/close"

    equal = await client.post(
        close_url,
        json={"ended_at": started.isoformat()},
        headers=idempotency_headers(),
    )
    before = await client.post(
        close_url,
        json={"ended_at": (started - timedelta(seconds=1)).isoformat()},
        headers=idempotency_headers(),
    )
    naive = await client.post(
        close_url,
        json={"ended_at": started.replace(tzinfo=None).isoformat()},
        headers=idempotency_headers(),
    )

    assert equal.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert equal.json()["reason"] == "invalid-rental-period"
    assert before.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert before.json()["reason"] == "invalid-rental-period"
    assert naive.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    close_key = "future-close-replay"
    future_end = datetime.now(tz=UTC) + timedelta(days=1)
    close_body = {"ended_at": future_end.isoformat()}
    closed = await client.post(
        close_url,
        json=close_body,
        headers=idempotency_headers(close_key),
    )
    replay = await client.post(
        close_url,
        json=close_body,
        headers=idempotency_headers(close_key),
    )
    repeated = await client.post(
        close_url,
        json=close_body,
        headers=idempotency_headers(),
    )

    assert closed.status_code == HTTPStatus.OK, closed.text
    assert closed.json()["is_active"] is False
    assert datetime.fromisoformat(closed.json()["ended_at"]) == future_end
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.content == closed.content
    assert repeated.status_code == HTTPStatus.CONFLICT
    assert repeated.json()["reason"] == "rental-already-closed"

    rental_detail = (await client.get(close_url.removesuffix("/close"))).json()
    transport_detail = (await client.get(f"/transport/{transport['id']}")).json()
    available = (await client.get("/transport", params={"is_available": True})).json()["items"]
    assert rental_detail["is_active"] is False
    assert transport_detail["is_available"] is True
    assert transport_detail["active_rental"] is None
    assert transport["id"] in {item["id"] for item in available}


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


async def test_bulk_delete_couriers_signed_contract_rolls_back_all_changes(
    client: AsyncClient,
) -> None:
    # Обычный курьер удаляется первым по UUID, даже при обратном порядке входных ID.
    courier_ids = sorted([await create_courier(), await create_courier()])
    ordinary_courier, protected_courier = courier_ids
    document_files = [await create_file() for _ in courier_ids]
    documents = [
        CourierDocument(
            id=uuid4(),
            courier_id=courier_id,
            file_id=file_id,
            type=DocumentType.PASSPORT,
            purpose=DocumentPurpose.EMPLOYMENT_COMPLIANCE,
        )
        for courier_id, file_id in zip(courier_ids, document_files, strict=True)
    ]
    accounts = [
        CourierPlatformAccount(
            id=uuid4(),
            courier_id=courier_id,
            platform=DeliveryPlatform.WOLT,
            status=PlatformAccountStatus.ACTIVE,
        )
        for courier_id in courier_ids
    ]
    async with session_module.session_factory() as session, session.begin():
        session.add_all([*documents, *accounts])

    transport = await create_transport(client, serial_number="bulk-delete-protected")
    contract_file = await create_file()
    rental = await create_rental(
        client,
        transport["id"],
        protected_courier,
        started_at=datetime.now(tz=UTC) - timedelta(days=1),
        file_id=contract_file,
    )
    assert rental.status_code == HTTPStatus.CREATED, rental.text
    key = "bulk-delete-signed-contract"

    response = await client.post(
        "/courier/bulk-delete",
        json={"courier_ids": [str(protected_courier), str(ordinary_courier)]},
        headers=idempotency_headers(key),
    )

    assert response.status_code == HTTPStatus.CONFLICT, response.text
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["reason"] == "signed-contract-protects-rental"
    assert response.json()["courier_id"] == str(protected_courier)
    async with session_module.session_factory() as session:
        for courier_id in courier_ids:
            assert await session.get(Courier, courier_id) is not None
        for document in documents:
            stored_document = await session.get(CourierDocument, document.id)
            assert stored_document is not None
            assert stored_document.courier_id == document.courier_id
            assert stored_document.file_id == document.file_id
        for account in accounts:
            stored_account = await session.get(CourierPlatformAccount, account.id)
            assert stored_account is not None
            assert stored_account.courier_id == account.courier_id
            assert stored_account.status is PlatformAccountStatus.ACTIVE
        for file_id in [*document_files, contract_file]:
            file = await session.get(File, file_id)
            assert file is not None and file.status is FileStatus.READY
        stored_rental = await session.get(CourierTransport, UUID(rental.json()["id"]))
        assert stored_rental is not None
        assert stored_rental.courier_id == protected_courier
        assert stored_rental.transport_id == UUID(transport["id"])
        assert stored_rental.file_id == contract_file
        assert await session.get(Transport, UUID(transport["id"])) is not None
        assert await session.get(IdempotencyKey, key) is None


async def test_bulk_delete_couriers_cascades_unsigned_rentals_preserving_transports(
    client: AsyncClient,
) -> None:
    courier_ids = [await create_courier(), await create_courier()]
    transports = [
        await create_transport(client, serial_number=f"bulk-delete-unsigned-{number}")
        for number in range(2)
    ]
    rental_ids = []
    for courier_id, transport in zip(courier_ids, transports, strict=True):
        rental = await create_rental(
            client,
            transport["id"],
            courier_id,
            started_at=datetime.now(tz=UTC) - timedelta(days=1),
        )
        assert rental.status_code == HTTPStatus.CREATED, rental.text
        rental_ids.append(UUID(rental.json()["id"]))

    response = await client.post(
        "/courier/bulk-delete",
        json={"courier_ids": [str(courier_id) for courier_id in courier_ids]},
        headers=idempotency_headers(),
    )

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == {"deleted_count": 2}
    async with session_module.session_factory() as session:
        for courier_id in courier_ids:
            assert await session.get(Courier, courier_id) is None
        for rental_id in rental_ids:
            assert await session.get(CourierTransport, rental_id) is None
        for transport in transports:
            assert await session.get(Transport, UUID(transport["id"])) is not None


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
        transport_constraints = set(
            (
                await session.scalars(
                    text(
                        "SELECT conname FROM pg_constraint WHERE conrelid = 'transports'::regclass"
                    )
                )
            ).all()
        )
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
    assert constraints["ck_courier_transports_payment_type_allowed"] == "c"
    assert {
        "ck_transports_comment_normalized",
        "ck_transports_debt_amount_non_negative",
        "ck_transports_ordinal_number_positive",
    } <= transport_constraints
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

    assert len(auth) == 16
    assert all(auth.values())
    assert idempotency == {
        ("POST", "/transport"),
        ("POST", "/transport/{transport_id}/components"),
        ("POST", "/transport/{transport_id}/rentals"),
        ("POST", "/transport/{transport_id}/rentals/{rental_id}/close"),
        ("POST", "/transport/{transport_id}/rentals/{rental_id}/contract"),
    }
    assert "/transport/{transport_id}/rentals/{rental_id}/contract" in app.openapi()["paths"]
    schemas = app.openapi()["components"]["schemas"]
    assert {"comment", "debt_amount"} <= schemas["TransportDetailResponse"]["properties"].keys()
    assert "comment" not in schemas["TransportListItemResponse"]["properties"]
    assert "debt_amount" not in schemas["TransportListItemResponse"]["properties"]
    assert "ordinal_number" in schemas["TransportListItemResponse"]["properties"]
    assert "ordinal_number" in schemas["TransportDetailResponse"]["properties"]
    assert "payment_type" in schemas["CourierTransportCreate"]["required"]
    assert schemas["CourierTransportPaymentPatch"]["required"] == ["payment_type"]
    assert schemas["RentalPaymentType"]["enum"] == ["monthly", "weekly", "weekly_in_arrears"]
    assert "patch" in app.openapi()["paths"]["/transport/{transport_id}/rentals/{rental_id}"]
