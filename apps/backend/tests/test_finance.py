"""Finance: CRUD чеков, защита File и публичный HTTP-контракт."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import delete, text, update

from app.kernel.db import session as session_module
from app.kernel.errors import Conflict
from app.kernel.idempotency import is_idempotent
from app.kernel.security.authentication import is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.finance.models import Receipt, ReceiptTag
from app.modules.finance.module import finance_module
from app.modules.storage.services import mark_for_deletion
from app.platform.files import File, FileStatus
from tests.asgi import app_client, build_app

ADMIN_ID: Final = UUID(int=601)
PROBLEM_JSON: Final = "application/problem+json"
RECEIPT_DATE: Final = "2026-08-30"


@pytest.fixture
async def finance_database(clean_db: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Убирать собственную таблицу до очистки общего File следующими тестами."""
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(Receipt))
        await session.execute(delete(ReceiptTag))
    try:
        yield
    finally:
        async with session_module.session_factory() as session, session.begin():
            await session.execute(delete(Receipt))
            await session.execute(delete(ReceiptTag))


@pytest.fixture
async def client(finance_database: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    """Клиент finance с действующим Admin access JWT."""
    async with app_client([finance_module], raise_app_exceptions=False) as http:
        access = issue_tokens(
            ADMIN_ID,
            settings=jwt_settings,
            claims={"kind": "admin"},
        ).access_token
        http.headers["authorization"] = f"Bearer {access}"
        yield http


def idempotency_headers(key: str | None = None) -> dict[str, str]:
    """Выдать уникальный ключ создания чека."""
    return {"Idempotency-Key": key or uuid4().hex}


async def create_file(status: FileStatus = FileStatus.READY) -> UUID:
    """Создать File нужного lifecycle-состояния напрямую."""
    file_id = uuid4()
    async with session_module.session_factory() as session, session.begin():
        session.add(
            File(
                id=file_id,
                bucket="receipts",
                key=str(file_id),
                original_name="receipt.pdf",
                content_type="application/pdf",
                size=128,
                etag="etag" if status is FileStatus.READY else None,
                status=status,
            )
        )
    return file_id


async def create_receipt(
    client: AsyncClient,
    *,
    file_id: UUID | None = None,
    amount: str = "1250.50",
    receipt_date: str = RECEIPT_DATE,
    tag_id: UUID | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    """Создать чек через публичный HTTP-контракт."""
    attached_file = file_id or await create_file()
    response = await client.post(
        "/receipts",
        json={
            "file_id": str(attached_file),
            "amount": amount,
            "date": receipt_date,
            "tag_id": str(tag_id) if tag_id else None,
        },
        headers=idempotency_headers(key),
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    payload: dict[str, Any] = response.json()
    return payload


async def create_tag(client: AsyncClient, name: str = "Топливо") -> dict[str, Any]:
    """Создать тег расхода через публичный HTTP-контракт."""
    response = await client.post(
        "/receipts/tags",
        json={"name": name},
        headers=idempotency_headers(),
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    payload: dict[str, Any] = response.json()
    return payload


async def test_every_finance_endpoint_requires_admin_jwt(client: AsyncClient) -> None:
    authorization = client.headers.pop("authorization")
    receipt_id = uuid4()
    requests = (
        ("POST", "/receipts"),
        ("GET", "/receipts"),
        ("POST", "/receipts/tags"),
        ("GET", "/receipts/tags"),
        ("GET", f"/receipts/tags/{receipt_id}"),
        ("PATCH", f"/receipts/tags/{receipt_id}"),
        ("DELETE", f"/receipts/tags/{receipt_id}"),
        ("GET", f"/receipts/{receipt_id}"),
        ("PATCH", f"/receipts/{receipt_id}"),
        ("DELETE", f"/receipts/{receipt_id}"),
    )
    try:
        for method, path in requests:
            response = await client.request(method, path, json={})
            assert response.status_code == HTTPStatus.UNAUTHORIZED, (method, path, response.text)
            assert response.headers["content-type"] == PROBLEM_JSON
            assert response.json()["reason"] == "missing-token"
    finally:
        client.headers["authorization"] = authorization


async def test_receipt_create_retrieve_replay_and_validation(client: AsyncClient) -> None:
    file_id = await create_file()
    body = {"file_id": str(file_id), "amount": "1250.50", "date": RECEIPT_DATE}
    created_response = await client.post(
        "/receipts",
        json=body,
        headers=idempotency_headers("receipt-replay"),
    )
    replay = await client.post(
        "/receipts",
        json=body,
        headers=idempotency_headers("receipt-replay"),
    )
    created = created_response.json()
    retrieved = await client.get(f"/receipts/{created['id']}")

    assert created_response.status_code == HTTPStatus.CREATED
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.content == created_response.content
    assert retrieved.json() == created
    assert created["file_id"] == str(file_id)
    assert created["amount"] == "1250.50"
    assert created["date"] == RECEIPT_DATE
    assert created["tag_id"] is None
    assert created["created_at"] == created["updated_at"]

    unknown_field = await client.post(
        "/receipts",
        json={**body, "currency": "CZK"},
        headers=idempotency_headers(),
    )
    zero = await client.post(
        "/receipts",
        json={**body, "amount": "0.00"},
        headers=idempotency_headers(),
    )
    bad_scale = await client.post(
        "/receipts",
        json={**body, "amount": "1.234"},
        headers=idempotency_headers(),
    )
    missing_date = await client.post(
        "/receipts",
        json={"file_id": str(file_id), "amount": "10.00"},
        headers=idempotency_headers(),
    )
    invalid_date = await client.post(
        "/receipts",
        json={**body, "date": "30.08.2026"},
        headers=idempotency_headers(),
    )
    null_date = await client.post(
        "/receipts",
        json={**body, "date": None},
        headers=idempotency_headers(),
    )

    assert unknown_field.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert zero.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_scale.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert missing_date.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid_date.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert null_date.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_receipt_tag_crud_uniqueness_and_replay(client: AsyncClient) -> None:
    response = await client.post(
        "/receipts/tags",
        json={"name": "  Топливо  "},
        headers=idempotency_headers("tag-replay"),
    )
    replay = await client.post(
        "/receipts/tags",
        json={"name": "  Топливо  "},
        headers=idempotency_headers("tag-replay"),
    )
    tag = response.json()
    listed = await client.get("/receipts/tags")
    retrieved = await client.get(f"/receipts/tags/{tag['id']}")
    renamed = await client.patch(f"/receipts/tags/{tag['id']}", json={"name": "Ремонт"})
    duplicate = await client.post(
        "/receipts/tags",
        json={"name": "ремонт"},
        headers=idempotency_headers(),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert tag["name"] == "Топливо"
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.content == response.content
    assert listed.json()["items"] == [tag]
    assert retrieved.json() == tag
    assert renamed.json()["name"] == "Ремонт"
    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.json()["reason"] == "receipt-tag-name-in-use"
    assert (await client.delete(f"/receipts/tags/{tag['id']}")).status_code == HTTPStatus.NO_CONTENT
    assert (await client.get(f"/receipts/tags/{tag['id']}")).status_code == HTTPStatus.NOT_FOUND


async def test_receipt_assigns_filters_clears_and_loses_deleted_tag(client: AsyncClient) -> None:
    fuel = await create_tag(client, "Топливо")
    repairs = await create_tag(client, "Ремонт")
    tagged = await create_receipt(client, tag_id=UUID(fuel["id"]))
    await create_receipt(client)

    filtered = await client.get("/receipts", params={"tag_id": fuel["id"]})
    changed = await client.patch(
        f"/receipts/{tagged['id']}",
        json={"tag_id": repairs["id"]},
    )
    cleared = await client.patch(f"/receipts/{tagged['id']}", json={"tag_id": None})
    restored = await client.patch(
        f"/receipts/{tagged['id']}",
        json={"tag_id": fuel["id"]},
    )
    deleted = await client.delete(f"/receipts/tags/{fuel['id']}")
    after_delete = await client.get(f"/receipts/{tagged['id']}")
    unknown = await client.patch(f"/receipts/{tagged['id']}", json={"tag_id": str(uuid4())})

    assert [item["id"] for item in filtered.json()["items"]] == [tagged["id"]]
    assert changed.json()["tag_id"] == repairs["id"]
    assert cleared.json()["tag_id"] is None
    assert restored.json()["tag_id"] == fuel["id"]
    assert deleted.status_code == HTTPStatus.NO_CONTENT
    assert after_delete.json()["tag_id"] is None
    assert after_delete.json()["updated_at"] != restored.json()["updated_at"]
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert unknown.json()["resource"] == "ReceiptTag"


async def test_receipt_requires_a_ready_unused_file(client: AsyncClient) -> None:
    pending_file = await create_file(FileStatus.PENDING)
    ready_file = await create_file()
    unknown = await client.post(
        "/receipts",
        json={"file_id": str(uuid4()), "amount": "10.00", "date": RECEIPT_DATE},
        headers=idempotency_headers(),
    )
    pending = await client.post(
        "/receipts",
        json={"file_id": str(pending_file), "amount": "10.00", "date": RECEIPT_DATE},
        headers=idempotency_headers(),
    )
    await create_receipt(client, file_id=ready_file)
    reused = await client.post(
        "/receipts",
        json={"file_id": str(ready_file), "amount": "20.00", "date": RECEIPT_DATE},
        headers=idempotency_headers(),
    )

    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert unknown.json()["resource"] == "File"
    assert pending.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert pending.json()["reason"] == "file-not-ready"
    assert reused.status_code == HTTPStatus.CONFLICT
    assert reused.json()["reason"] == "receipt-file-in-use"


async def test_receipt_keyset_patch_and_delete(client: AsyncClient) -> None:
    receipts = [await create_receipt(client, amount=f"{number + 1}.00") for number in range(3)]
    moment = datetime.now(tz=UTC)
    async with session_module.session_factory() as session, session.begin():
        await session.execute(update(Receipt).values(created_at=moment))

    first = (await client.get("/receipts", params={"limit": 2})).json()
    rest = (await client.get("/receipts", params={"cursor": first["next_cursor"]})).json()
    ids = [item["id"] for item in first["items"] + rest["items"]]

    assert len(ids) == len(set(ids)) == 3
    assert rest["next_cursor"] is None

    replacement_file = await create_file()
    patched = await client.patch(
        f"/receipts/{receipts[0]['id']}",
        json={
            "file_id": str(replacement_file),
            "amount": "99.90",
            "date": "2025-12-31",
        },
    )
    explicit_null = await client.patch(
        f"/receipts/{receipts[0]['id']}",
        json={"date": None},
    )

    assert patched.status_code == HTTPStatus.OK
    assert patched.json()["file_id"] == str(replacement_file)
    assert patched.json()["amount"] == "99.90"
    assert patched.json()["date"] == "2025-12-31"
    assert explicit_null.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    removed = await client.delete(f"/receipts/{receipts[0]['id']}")
    repeated = await client.delete(f"/receipts/{receipts[0]['id']}")
    assert removed.status_code == HTTPStatus.NO_CONTENT
    assert not removed.content
    assert repeated.status_code == HTTPStatus.NOT_FOUND


async def test_receipt_protects_its_file_from_deletion(client: AsyncClient) -> None:
    file_id = await create_file()
    receipt = await create_receipt(client, file_id=file_id)

    with pytest.raises(Conflict) as captured:
        await mark_for_deletion(file_id, session_factory=session_module.session_factory)

    assert captured.value.extra["reason"] == "file-in-use"
    assert (await client.delete(f"/receipts/{receipt['id']}")).status_code == HTTPStatus.NO_CONTENT

    await mark_for_deletion(file_id, session_factory=session_module.session_factory)
    async with session_module.session_factory() as session:
        file = await session.get(File, file_id)
    assert file is not None and file.status is FileStatus.DELETING


async def test_postgresql_constraints_triggers_and_index(finance_database: None) -> None:  # noqa: ARG001
    async with session_module.session_factory() as session:
        constraints = set(
            (
                await session.scalars(
                    text("SELECT conname FROM pg_constraint WHERE conrelid = 'receipts'::regclass")
                )
            ).all()
        )
        triggers = set(
            (
                await session.scalars(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE NOT tgisinternal AND tgrelid IN "
                        "('receipts'::regclass, 'files'::regclass)"
                    )
                )
            ).all()
        )
        index_definition = await session.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'receipts' AND indexname = 'ix_receipts_keyset'"
            )
        )
        date_column = (
            await session.execute(
                text(
                    "SELECT data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'receipts' "
                    "AND column_name = 'date'"
                )
            )
        ).one()
        tag_column = (
            await session.execute(
                text(
                    "SELECT data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'receipts' "
                    "AND column_name = 'tag_id'"
                )
            )
        ).one()
        tag_indexes = set(
            (
                await session.scalars(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE indexname IN "
                        "('ix_receipts_tag_keyset', 'ix_receipt_tags_keyset', "
                        "'uq_receipt_tags_name_ci')"
                    )
                )
            ).all()
        )

    assert {
        "ck_receipts_amount_positive",
        "fk_receipts_file_id_files",
        "fk_receipts_tag_id_receipt_tags",
        "uq_receipts_file_id",
    } <= constraints
    assert {
        "finance_require_ready_receipt_file",
        "finance_protect_receipt_file",
    } <= triggers
    assert index_definition is not None
    assert "created_at DESC, id DESC" in index_definition
    assert tuple(date_column) == ("date", "NO")
    assert tuple(tag_column) == ("uuid", "YES")
    assert tag_indexes == {
        "ix_receipts_tag_keyset",
        "ix_receipt_tags_keyset",
        "uq_receipt_tags_name_ci",
    }


def test_manifest_route_markers_and_openapi_contract() -> None:
    app = build_app([finance_module])
    assert finance_module.url_prefix == "/receipts"
    assert finance_module.models == "app.modules.finance.models"
    assert finance_module.router is not None

    auth = {}
    idempotency = set()
    for route in finance_module.router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            key = (method, f"{finance_module.url_prefix}{route.path}")
            auth[key] = is_authenticated(route.endpoint)
            if is_idempotent(route.endpoint):
                idempotency.add(key)

    assert len(auth) == 10
    assert all(auth.values())
    assert idempotency == {("POST", "/receipts"), ("POST", "/receipts/tags")}
    openapi = app.openapi()
    assert "/receipts" in openapi["paths"]
    assert set(openapi["components"]["schemas"]["ReceiptCreate"]["required"]) == {
        "file_id",
        "amount",
        "date",
    }
    assert "tag_id" not in openapi["components"]["schemas"]["ReceiptCreate"]["required"]
    assert openapi["components"]["schemas"]["ReceiptResponse"]["properties"]["tag_id"]["anyOf"] == [
        {"type": "string", "format": "uuid"},
        {"type": "null"},
    ]
    assert openapi["components"]["schemas"]["ReceiptResponse"]["properties"]["date"] == {
        "type": "string",
        "format": "date",
        "title": "Date",
    }
