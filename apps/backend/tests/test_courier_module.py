"""Courier aggregate: multipart upload, natural keys, lifecycle и retention."""

import asyncio
import dataclasses
import io
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.kernel.config import settings
from app.kernel.context import request_id
from app.kernel.db import session as session_module
from app.kernel.events.models import OutboxMessage
from app.kernel.idempotency import IdempotencyKey, is_idempotent
from app.kernel.security.authentication import is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.courier_module import handlers as courier_handlers
from app.modules.courier_module.models import (
    Courier,
    CourierDocument,
    CourierPlatformAccount,
    DeliveryPlatform,
    DocumentPurpose,
    DocumentType,
    PlatformAccountStatus,
)
from app.modules.courier_module.module import courier_lifespan, courier_module
from app.modules.courier_module.schemas.requests import CourierAggregateCreate
from app.modules.courier_module.services import (
    CourierModuleSettings,
    create_courier_aggregate,
    purge_expired_documents,
)
from app.modules.courier_module.tasks import purge_expired_documents as retention_task
from app.platform.files import (
    File,
    FilePolicy,
    FileStatus,
    FileUploadStaging,
    MultipartUploader,
    StagingStatus,
)
from app.platform.s3 import ObjectStorage, S3Settings, storage
from app.platform.taskiq import SCHEDULE_ATTR, task_name
from tests.asgi import app_client, build_app

PNG: Final = "image/png"
PROBLEM_JSON: Final = "application/problem+json"
ADMIN_ID: Final = UUID(int=103)
POLICY: Final = FilePolicy(
    max_file_size=1024,
    allowed_content_types=frozenset({PNG, "application/pdf"}),
)
TEST_SETTINGS: Final = CourierModuleSettings(
    max_documents=3,
    max_total_upload_size=2048,
    retention_platform_onboarding_days=90,
    retention_employment_compliance_days=1825,
    retention_other_days=365,
    retention_batch_size=100,
)
BASE_COURIER: Final[dict[str, Any]] = {
    "full_name": "Eva Novak",
    "email": " EVA@EXAMPLE.COM ",
    "phone": "+420 777-111-222",
    "date_of_birth": "1994-04-12",
    "city": "Praha",
    "consent_to_processing": True,
    "platform_accounts": [{"platform": "wolt"}],
    "documents": [
        {
            "type": "passport",
            "purpose": "platform_onboarding",
        }
    ],
}
BULK_OPERATIONS: Final[tuple[tuple[str, str, dict[str, str]], ...]] = (
    ("POST", "/courier/bulk-delete", {}),
    ("PATCH", "/courier/bulk-status", {"platform": "wolt", "status": "active"}),
)


@dataclass
class TransactionWatch:
    """Синхронные Session и запросы, открывавшие их транзакции."""

    sessions: dict[Session, str] = field(default_factory=dict)

    def open_now(self) -> list[Session]:
        """Проверять свой запрос, не транзакции соседних HTTP-запросов."""
        return [
            session
            for session, owner in self.sessions.items()
            if owner == request_id.get() and session.in_transaction()
        ]


def guarded(method: Any, name: str, watch: TransactionWatch) -> Any:
    """Обернуть S3 primitive проверкой отсутствия DB-транзакции."""

    async def call(self: ObjectStorage, *args: Any, **kwargs: Any) -> Any:
        assert not watch.open_now(), (
            f"ObjectStorage.{name} called while a database transaction was open"
        )
        return await method(self, *args, **kwargs)

    return call


@pytest.fixture(autouse=True)
def guard_transactions(monkeypatch: pytest.MonkeyPatch) -> Iterator[TransactionWatch]:
    """Сторожить все S3-вызовы courier_module, как требует transactions rule."""
    watch = TransactionWatch()

    def track(session: Session, _transaction: Any, _connection: Any) -> None:
        watch.sessions[session] = request_id.get()

    event.listen(Session, "after_begin", track)
    for name in (
        "create_multipart_upload",
        "upload_part",
        "complete_multipart_upload",
        "abort_multipart_upload",
    ):
        monkeypatch.setattr(
            ObjectStorage,
            name,
            guarded(getattr(ObjectStorage, name), name, watch),
        )
    yield watch
    event.remove(Session, "after_begin", track)


@pytest.fixture
async def bucket(minio_endpoint: str) -> AsyncIterator[S3Settings]:
    """Отдельный bucket реального MinIO для каждого теста."""
    config = S3Settings(endpoint_url=minio_endpoint, bucket=f"courier-{uuid4().hex[:8]}")
    async with storage(config) as objects:
        await objects.client.create_bucket(Bucket=config.bucket)
    yield config


@pytest.fixture
async def sessions(clean_db: None) -> async_sessionmaker[AsyncSession]:  # noqa: ARG001
    """Очистить новые aggregate-таблицы и вернуть настоящую factory."""
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(Courier))
    return session_module.session_factory


@pytest.fixture
async def client(
    bucket: S3Settings,
    sessions: async_sessionmaker[AsyncSession],  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент courier_module с тестовыми S3 policy и limits."""
    monkeypatch.setattr(courier_handlers, "courier_module_settings", TEST_SETTINGS)
    module = dataclasses.replace(
        courier_module,
        lifespan=courier_lifespan(storage_config=bucket, policy=POLICY),
    )
    async with app_client(
        [module],
        lifespan=True,
        raise_app_exceptions=False,
    ) as http:
        access = issue_tokens(
            ADMIN_ID,
            settings=jwt_settings,
            claims={"kind": "admin"},
        ).access_token
        http.headers["authorization"] = f"Bearer {access}"
        yield http


def multipart(
    payload: dict[str, Any],
    contents: Sequence[bytes] = (b"document",),
) -> dict[str, Any]:
    """Собрать kwargs httpx для aggregate multipart contract."""
    return {
        "data": {"payload": json.dumps(payload)},
        "files": [
            ("files", (f"document-{index}.png", content, PNG))
            for index, content in enumerate(contents)
        ],
    }


async def post_courier(
    client: AsyncClient,
    payload: dict[str, Any] | None = None,
    contents: Sequence[bytes] = (b"document",),
) -> Any:
    """Создать Courier aggregate и вернуть HTTP response."""
    return await client.post("/courier", **multipart(payload or BASE_COURIER, contents))


async def test_create_is_public_and_every_other_route_requires_bearer(
    client: AsyncClient,
) -> None:
    authorization = client.headers.pop("authorization")
    try:
        payload = {**BASE_COURIER, "documents": []}
        created = await post_courier(client, payload, ())

        assert created.status_code == HTTPStatus.CREATED, created.text
        courier = created.json()
        account_id = courier["platform_accounts"][0]["id"]
        document_id = uuid4()
        protected_requests: tuple[tuple[str, str, dict[str, Any]], ...] = (
            ("GET", "/courier", {}),
            ("GET", f"/courier/{courier['id']}", {}),
            ("PATCH", f"/courier/{courier['id']}", {"json": {}}),
            ("DELETE", f"/courier/{courier['id']}", {}),
            (
                "POST",
                "/courier/bulk-delete",
                {"json": {"courier_ids": [courier["id"]]}},
            ),
            (
                "PATCH",
                "/courier/bulk-status",
                {
                    "json": {
                        "courier_ids": [courier["id"]],
                        "platform": "wolt",
                        "status": "active",
                    }
                },
            ),
            (
                "POST",
                f"/courier/{courier['id']}/platform-accounts",
                {"json": {"platform": "foodora"}},
            ),
            (
                "PATCH",
                f"/courier/{courier['id']}/platform-accounts/{account_id}",
                {"json": {"status": "active"}},
            ),
            (
                "POST",
                f"/courier/{courier['id']}/documents",
                {
                    "data": {
                        "payload": json.dumps(
                            {"type": "identity_card", "purpose": "platform_onboarding"}
                        )
                    },
                    "files": {"file": ("identity.png", b"identity", PNG)},
                },
            ),
            (
                "PATCH",
                f"/courier/{courier['id']}/documents/{document_id}",
                {"json": {"purpose": "other"}},
            ),
            (
                "DELETE",
                f"/courier/{courier['id']}/documents/{document_id}",
                {},
            ),
        )

        for method, path, kwargs in protected_requests:
            response = await client.request(method, path, **kwargs)

            assert response.status_code == HTTPStatus.UNAUTHORIZED, (
                method,
                path,
                response.text,
            )
            assert response.headers["content-type"] == PROBLEM_JSON
            assert response.json() == {
                "type": f"{settings.errors_base_url}/unauthorized",
                "title": "Unauthorized",
                "status": HTTPStatus.UNAUTHORIZED,
                "detail": "Authentication is required for this operation",
                "instance": path,
                "request_id": response.headers["x-request-id"],
                "reason": "missing-token",
            }
    finally:
        client.headers["authorization"] = authorization


async def counts() -> tuple[int, int, int, int, int]:
    """Количество Courier/Account/Document/File/Staging строк."""
    async with session_module.session_factory() as session:
        values = []
        for model in (
            Courier,
            CourierPlatformAccount,
            CourierDocument,
            File,
            FileUploadStaging,
        ):
            values.append((await session.scalars(select(func.count()).select_from(model))).one())
    return tuple(values)  # type: ignore[return-value]


async def stored_file(file_id: UUID) -> File:
    """Вернуть обязательную строку File."""
    async with session_module.session_factory() as session:
        file = await session.get(File, file_id)
    assert file is not None
    return file


async def registration_payloads() -> list[dict[str, Any]]:
    """Вернуть payload всех courier.registered в порядке outbox."""
    async with session_module.session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(OutboxMessage.payload)
                    .where(OutboxMessage.topic == "courier.registered")
                    .order_by(OutboxMessage.occurred_at, OutboxMessage.id)
                )
            ).all()
        )


@contextmanager
def failing_final_transaction() -> Iterator[None]:
    """Ронять final transaction после отправки ORM INSERT в PostgreSQL."""

    def boom(_session: Session, _flush_context: Any) -> None:
        raise RuntimeError("final transaction refused")

    event.listen(Session, "after_flush", boom)
    try:
        yield
    finally:
        event.remove(Session, "after_flush", boom)


async def test_aggregate_post_uploads_and_commits_all_rows(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    payload = {
        **BASE_COURIER,
        "contact_platform": "telegram",
        "contact": "@eva",
        "platform_accounts": [
            {"platform": "wolt"},
            {"platform": "foodora"},
            {"platform": "bolt_food"},
        ],
    }
    response = await post_courier(client, payload)

    assert response.status_code == HTTPStatus.CREATED, response.text
    body = response.json()
    assert (body["email"], body["phone"]) == ("eva@example.com", "+420777111222")
    assert body["consent_at"] is not None
    assert body["platform_accounts"][0]["status"] == "pending"
    assert len(body["documents"]) == 1
    nested = body["documents"][0]["file"]
    assert nested["status"] == "ready"
    assert "bucket" not in nested and "key" not in nested
    assert await counts() == (1, 3, 1, 1, 0)

    file = await stored_file(UUID(nested["id"]))
    assert (file.bucket, file.etag, file.size) == (bucket.bucket, nested["etag"], 8)
    async with storage(bucket) as objects:
        assert await objects.head_object(file.key, bucket=file.bucket) is not None

    async with session_module.session_factory() as session:
        topics = list((await session.scalars(select(OutboxMessage.topic))).all())
    assert sorted(topics) == ["courier.registered", "file.confirmed"]
    assert await registration_payloads() == [
        {
            "courier_id": body["id"],
            "full_name": "Eva Novak",
            "contact_platform": "telegram",
            "contact": "@eva",
            "platforms": ["wolt", "foodora", "bolt_food"],
        }
    ]


async def test_courier_and_registration_event_share_final_transaction(
    bucket: S3Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Ошибка после INSERT Courier откатывает Courier, account и outbox."""
    payload = {**BASE_COURIER, "documents": []}
    request = CourierAggregateCreate.model_validate(payload)

    async with storage(bucket) as objects:
        with (
            failing_final_transaction(),
            pytest.raises(
                RuntimeError,
                match="final transaction refused",
            ),
        ):
            await create_courier_aggregate(
                request,
                [],
                session_factory=sessions,
                uploader=MultipartUploader(objects=objects, policy=POLICY),
                settings=TEST_SETTINGS,
            )

    assert await counts() == (0, 0, 0, 0, 0)
    assert await registration_payloads() == []


async def test_natural_key_retry_returns_saved_aggregate_without_s3(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await post_courier(client)
    original = created.json()

    async def forbidden(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("natural-key hit must not start multipart upload")

    monkeypatch.setattr(ObjectStorage, "create_multipart_upload", forbidden)
    retry_payload = {
        **BASE_COURIER,
        "full_name": "Must not replace saved data",
        "email": "eva@example.com",
        "phone": "+420999888777",
        "platform_accounts": [{"platform": "bolt_food"}],
    }
    response = await post_courier(client, retry_payload, (b"other",))

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == original
    assert await counts() == (1, 1, 1, 1, 0)
    assert len(await registration_payloads()) == 1


async def test_identity_split_is_conflict(client: AsyncClient) -> None:
    first = {**BASE_COURIER, "documents": []}
    second = {
        **first,
        "email": "second@example.com",
        "phone": "+420700000002",
    }
    assert (await post_courier(client, first, ())).status_code == HTTPStatus.CREATED
    assert (await post_courier(client, second, ())).status_code == HTTPStatus.CREATED

    split = {
        **first,
        "email": first["email"],
        "phone": second["phone"],
    }
    response = await post_courier(client, split, ())

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["reason"] == "identity-split"


async def test_concurrent_same_post_creates_one_aggregate_and_cleanup_staging(
    client: AsyncClient,
) -> None:
    first, second = await asyncio.gather(post_courier(client), post_courier(client))

    assert sorted((first.status_code, second.status_code)) == [HTTPStatus.OK, HTTPStatus.CREATED]
    assert first.json()["id"] == second.json()["id"]
    assert await counts() == (1, 1, 1, 1, 1)
    async with session_module.session_factory() as session:
        status = await session.scalar(select(FileUploadStaging.status))
    assert status is StagingStatus.DELETING
    assert len(await registration_payloads()) == 1


async def test_s3_failure_leaves_only_durable_staging(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_part(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("object store unavailable")

    monkeypatch.setattr(ObjectStorage, "upload_part", fail_part)
    response = await post_courier(client)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.headers["content-type"].startswith("application/problem+json")
    assert await counts() == (0, 0, 0, 0, 1)


@pytest.mark.parametrize(
    ("payload", "contents", "reason"),
    [
        (
            {
                **BASE_COURIER,
                "platform_accounts": [{"platform": "wolt"}, {"platform": "wolt"}],
            },
            (b"document",),
            None,
        ),
        ({**BASE_COURIER, "documents": []}, (b"unexpected",), "document-file-count-mismatch"),
        ({**BASE_COURIER, "owner_id": str(uuid4())}, (b"document",), None),
    ],
)
async def test_invalid_aggregate_is_problem_422_before_s3(
    client: AsyncClient,
    payload: dict[str, Any],
    contents: Sequence[bytes],
    reason: str | None,
) -> None:
    response = await post_courier(client, payload, contents)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.headers["content-type"].startswith("application/problem+json")
    if reason is not None:
        assert response.json()["reason"] == reason
    assert await counts() == (0, 0, 0, 0, 0)


async def test_empty_and_too_large_files_leave_staging_for_cleanup(
    client: AsyncClient,
) -> None:
    empty = await post_courier(client, contents=(b"",))
    assert empty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert empty.json()["reason"] == "empty_file"

    too_large = await post_courier(
        client,
        {**BASE_COURIER, "email": "large@example.com", "phone": "+420700000009"},
        (b"x" * 1025,),
    )
    assert too_large.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert too_large.json()["reason"] == "file_too_large"
    assert await counts() == (0, 0, 0, 0, 2)


async def test_get_list_keyset_and_deleting_filter(client: AsyncClient) -> None:
    first = (await post_courier(client)).json()
    second_payload = {
        **BASE_COURIER,
        "email": "second@example.com",
        "phone": "+420700000002",
        "full_name": "Second Courier",
    }
    second = (await post_courier(client, second_payload)).json()
    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    async with session_module.session_factory() as session, session.begin():
        await session.execute(update(Courier).values(created_at=same_time))
        await session.execute(
            update(File)
            .where(File.id == UUID(first["documents"][0]["file"]["id"]))
            .values(status=FileStatus.DELETING)
        )

    item = await client.get(f"/courier/{first['id']}")
    page = await client.get("/courier", params={"limit": 1})
    rest = await client.get(
        "/courier",
        params={"limit": 1, "cursor": page.json()["next_cursor"]},
    )

    assert item.json()["documents"] == []
    assert {page.json()["items"][0]["id"], rest.json()["items"][0]["id"]} == {
        first["id"],
        second["id"],
    }
    assert rest.json()["next_cursor"] is None
    filtered = await client.get("/courier", params={"email": " SECOND@EXAMPLE.COM "})
    assert [row["id"] for row in filtered.json()["items"]] == [second["id"]]

    activated = await client.patch(
        f"/courier/{first['id']}/platform-accounts/{first['platform_accounts'][0]['id']}",
        json={"status": "active"},
    )
    assert activated.status_code == HTTPStatus.OK
    status_filtered = await client.get("/courier", params={"status": "active"})
    assert [row["id"] for row in status_filtered.json()["items"]] == [first["id"]]


async def test_eager_query_count_does_not_grow_with_page_size(
    client: AsyncClient,
) -> None:
    await post_courier(client)
    second = {
        **BASE_COURIER,
        "email": "second@example.com",
        "phone": "+420700000002",
    }
    await post_courier(client, second)

    statements: list[str] = []

    def count_sql(
        _connection: Connection,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(session_module.engine.sync_engine, "before_cursor_execute", count_sql)
    try:
        response = await client.get("/courier", params={"limit": 2})
    finally:
        event.remove(session_module.engine.sync_engine, "before_cursor_execute", count_sql)

    assert response.status_code == HTTPStatus.OK
    selects = [statement for statement in statements if statement.lstrip().startswith("SELECT")]
    assert len(selects) == 3


async def test_patch_consent_normalization_and_unique_conflict(client: AsyncClient) -> None:
    created = (await post_courier(client)).json()
    second_payload = {
        **BASE_COURIER,
        "email": "second@example.com",
        "phone": "+420700000002",
    }
    second = (await post_courier(client, second_payload)).json()

    revoked = await client.patch(
        f"/courier/{created['id']}",
        json={
            "email": " NEW@EXAMPLE.COM ",
            "phone": "+420 (700) 000-003",
            "consent_to_processing": False,
        },
    )
    assert revoked.status_code == HTTPStatus.OK, revoked.text
    assert (revoked.json()["email"], revoked.json()["phone"]) == (
        "new@example.com",
        "+420700000003",
    )
    assert revoked.json()["consent_at"] is None

    granted = await client.patch(f"/courier/{created['id']}", json={"consent_to_processing": True})
    first_consent_at = granted.json()["consent_at"]
    repeated = await client.patch(f"/courier/{created['id']}", json={"consent_to_processing": True})
    assert repeated.json()["consent_at"] == first_consent_at

    conflict = await client.patch(f"/courier/{created['id']}", json={"email": second["email"]})
    assert conflict.status_code == HTTPStatus.CONFLICT
    assert conflict.json()["field"] == "email"
    assert (
        await client.patch(f"/courier/{created['id']}", json={"date_of_birth": "2999-01-01"})
    ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_platform_account_nested_writes_and_parent_scope(client: AsyncClient) -> None:
    first = (await post_courier(client)).json()
    second_payload = {
        **BASE_COURIER,
        "email": "second@example.com",
        "phone": "+420700000002",
    }
    second = (await post_courier(client, second_payload)).json()
    registrations_before = await registration_payloads()

    added = await client.post(
        f"/courier/{first['id']}/platform-accounts",
        json={"platform": "bolt_food"},
    )
    assert added.status_code == HTTPStatus.CREATED
    duplicate = await client.post(
        f"/courier/{first['id']}/platform-accounts",
        json={"platform": "bolt_food"},
    )
    assert duplicate.status_code == HTTPStatus.CONFLICT

    patched = await client.patch(
        f"/courier/{first['id']}/platform-accounts/{added.json()['id']}",
        json={"status": "active"},
    )
    assert patched.json()["status"] == "active"
    wrong_parent = await client.patch(
        f"/courier/{second['id']}/platform-accounts/{added.json()['id']}",
        json={"status": "inactive"},
    )
    assert wrong_parent.status_code == HTTPStatus.NOT_FOUND
    assert await registration_payloads() == registrations_before


async def test_document_upload_patch_and_delete(client: AsyncClient) -> None:
    payload = {**BASE_COURIER, "documents": []}
    courier = (await post_courier(client, payload, ())).json()
    metadata = {
        "type": "identity_card",
        "purpose": "employment_compliance",
    }
    added = await client.post(
        f"/courier/{courier['id']}/documents",
        data={"payload": json.dumps(metadata)},
        files={"file": ("identity.png", b"identity", PNG)},
    )

    assert added.status_code == HTTPStatus.CREATED, added.text
    assert added.json()["file"]["status"] == "ready"
    document_id = added.json()["id"]
    file_id = UUID(added.json()["file_id"])
    patched = await client.patch(
        f"/courier/{courier['id']}/documents/{document_id}",
        json={"purpose": "other", "legal_hold_until": "2030-01-01T00:00:00Z"},
    )
    assert (patched.json()["purpose"], patched.json()["legal_hold_until"]) == (
        "other",
        "2030-01-01T00:00:00Z",
    )

    removed = await client.delete(f"/courier/{courier['id']}/documents/{document_id}")
    assert removed.status_code == HTTPStatus.NO_CONTENT
    assert (await stored_file(file_id)).status is FileStatus.DELETING
    item = await client.get(f"/courier/{courier['id']}")
    assert item.json()["documents"] == []


async def test_delete_courier_cascades_children_and_marks_files(client: AsyncClient) -> None:
    created = (await post_courier(client)).json()
    file_id = UUID(created["documents"][0]["file_id"])

    response = await client.delete(f"/courier/{created['id']}")

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert await counts() == (0, 0, 0, 1, 0)
    assert (await stored_file(file_id)).status is FileStatus.DELETING
    assert (await client.delete(f"/courier/{created['id']}")).status_code == HTTPStatus.NOT_FOUND


async def seed_bulk_couriers(count: int = 2) -> list[Courier]:
    """Создать пачку без S3 с pending-регистрациями на всех платформах."""
    couriers = [
        Courier(
            id=uuid4(),
            full_name=f"Bulk Courier {index}",
            email=f"bulk-{index}@example.com",
            phone=f"+420700{index:06d}",
            date_of_birth=datetime(1990, 1, 1, tzinfo=UTC).date(),
            platform_accounts=[
                CourierPlatformAccount(platform=platform, status=PlatformAccountStatus.PENDING)
                for platform in DeliveryPlatform
            ],
        )
        for index in range(count)
    ]
    async with session_module.session_factory() as session, session.begin():
        session.add_all(couriers)
    return sorted(couriers, key=lambda courier: courier.id)


async def test_bulk_delete_cascades_files_and_replays(client: AsyncClient) -> None:
    couriers = [
        (await post_courier(client)).json(),
        (
            await post_courier(
                client,
                {**BASE_COURIER, "email": "second@example.com", "phone": "+420700000002"},
            )
        ).json(),
    ]
    unselected = (await seed_bulk_couriers(1))[0]
    body = {"courier_ids": [courier["id"] for courier in couriers]}
    headers = {"Idempotency-Key": "bulk-delete"}
    response = await client.post("/courier/bulk-delete", json=body, headers=headers)

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == {"deleted_count": 2}
    assert await counts() == (1, 3, 0, 2, 0)
    for courier in couriers:
        file = await stored_file(UUID(courier["documents"][0]["file_id"]))
        assert file.status is FileStatus.DELETING
    assert (await client.get(f"/courier/{unselected.id}")).status_code == HTTPStatus.OK

    replay = await client.post("/courier/bulk-delete", json=body, headers=headers)
    assert replay.status_code == HTTPStatus.OK
    assert replay.json() == response.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    retry = await client.post(
        "/courier/bulk-delete", json=body, headers={"Idempotency-Key": "new-delete"}
    )
    assert retry.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("platform", list(DeliveryPlatform))
@pytest.mark.parametrize("status", list(PlatformAccountStatus))
async def test_bulk_status_platform_scope_counts_and_replay(
    client: AsyncClient, platform: DeliveryPlatform, status: PlatformAccountStatus
) -> None:
    first, second, unselected = await seed_bulk_couriers(3)
    async with session_module.session_factory() as session, session.begin():
        await session.execute(
            update(CourierPlatformAccount)
            .where(
                CourierPlatformAccount.courier_id == first.id,
                CourierPlatformAccount.platform == platform,
            )
            .values(status=status)
        )
        if status is PlatformAccountStatus.PENDING:
            await session.execute(
                update(CourierPlatformAccount)
                .where(
                    CourierPlatformAccount.courier_id == second.id,
                    CourierPlatformAccount.platform == platform,
                )
                .values(status=PlatformAccountStatus.INACTIVE)
            )
    before = (await client.get(f"/courier/{first.id}")).json()
    body = {"courier_ids": [str(first.id), str(second.id)], "platform": platform, "status": status}
    headers = {"Idempotency-Key": "bulk-status"}
    response = await client.patch("/courier/bulk-status", json=body, headers=headers)

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == {"updated_count": 1, "unchanged_count": 1}
    assert (await client.get(f"/courier/{first.id}")).json() == before
    async with session_module.session_factory() as session:
        accounts = (await session.scalars(select(CourierPlatformAccount))).all()
    for account in accounts:
        expected = (
            status
            if account.courier_id != unselected.id and account.platform == platform
            else PlatformAccountStatus.PENDING
        )
        assert account.status is expected
    assert await registration_payloads() == []

    replay = await client.patch("/courier/bulk-status", json=body, headers=headers)
    assert replay.json() == response.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    noop = await client.patch(
        "/courier/bulk-status", json=body, headers={"Idempotency-Key": "new-status"}
    )
    assert noop.json() == {"updated_count": 0, "unchanged_count": 2}


@pytest.mark.parametrize(("method", "path", "extra"), BULK_OPERATIONS)
@pytest.mark.parametrize("size", [1, 100])
async def test_bulk_size_boundaries(
    client: AsyncClient, method: str, path: str, extra: dict[str, str], size: int
) -> None:
    couriers = await seed_bulk_couriers(size)
    response = await client.request(
        method,
        path,
        json={"courier_ids": [str(courier.id) for courier in couriers], **extra},
        headers={"Idempotency-Key": "bulk-boundary"},
    )

    assert response.status_code == HTTPStatus.OK, response.text
    expected = (
        {"deleted_count": size}
        if method == "POST"
        else {"updated_count": size, "unchanged_count": 0}
    )
    assert response.json() == expected


@pytest.mark.parametrize(("method", "path", "extra"), BULK_OPERATIONS)
@pytest.mark.parametrize(
    "invalid",
    [
        {"courier_ids": []},
        {"courier_ids": [str(UUID(int=index)) for index in range(101)]},
        {"courier_ids": [str(UUID(int=1)), str(UUID(int=1))]},
        {"courier_ids": ["not-a-uuid"]},
        {"courier_ids": None},
        {"courier_ids": str(UUID(int=1))},
        {"unexpected": True},
    ],
)
async def test_bulk_invalid_selection_does_not_write(
    client: AsyncClient,
    method: str,
    path: str,
    extra: dict[str, str],
    invalid: dict[str, Any],
) -> None:
    created = (await post_courier(client)).json()
    response = await client.request(
        method,
        path,
        json={"courier_ids": [created["id"]], **extra, **invalid},
        headers={"Idempotency-Key": "invalid-selection"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, response.text
    assert response.headers["content-type"] == PROBLEM_JSON
    assert (await client.get(f"/courier/{created['id']}")).json() == created
    async with session_module.session_factory() as session:
        assert await session.get(IdempotencyKey, "invalid-selection") is None


@pytest.mark.parametrize("field", ["platform", "status"])
@pytest.mark.parametrize("value", [None, "invalid", ""])
async def test_bulk_status_requires_valid_platform_and_status(
    client: AsyncClient, field: str, value: str | None
) -> None:
    created = (await post_courier(client)).json()
    body = {"courier_ids": [created["id"]], "platform": "wolt", "status": "active"}
    invalid = {**body, field: value}
    for payload in (invalid, {key: item for key, item in body.items() if key != field}):
        response = await client.patch(
            "/courier/bulk-status",
            json=payload,
            headers={"Idempotency-Key": "invalid-status"},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, response.text
    assert (await client.get(f"/courier/{created['id']}")).json() == created


@pytest.mark.parametrize(("method", "path", "extra"), BULK_OPERATIONS)
async def test_bulk_missing_courier_preserves_aggregate_and_releases_key(
    client: AsyncClient, method: str, path: str, extra: dict[str, str]
) -> None:
    created = (await post_courier(client)).json()
    missing = str(uuid4())
    response = await client.request(
        method,
        path,
        json={"courier_ids": [created["id"], missing], **extra},
        headers={"Idempotency-Key": "missing-courier"},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND, response.text
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["courier_ids"] == [missing]
    assert (await client.get(f"/courier/{created['id']}")).json() == created
    async with session_module.session_factory() as session:
        assert await session.get(IdempotencyKey, "missing-courier") is None
    retry = await client.request(
        method,
        path,
        json={"courier_ids": [created["id"]], **extra},
        headers={"Idempotency-Key": "missing-courier"},
    )
    assert retry.status_code == HTTPStatus.OK, retry.text


async def test_bulk_missing_platform_is_atomic_and_does_not_create_account(
    client: AsyncClient,
) -> None:
    first, second = await seed_bulk_couriers()
    async with session_module.session_factory() as session, session.begin():
        await session.execute(
            delete(CourierPlatformAccount).where(
                CourierPlatformAccount.courier_id == second.id,
                CourierPlatformAccount.platform == DeliveryPlatform.WOLT,
            )
        )
    body = {"courier_ids": [str(first.id), str(second.id)], "platform": "wolt", "status": "active"}
    response = await client.patch(
        "/courier/bulk-status", json=body, headers={"Idempotency-Key": "missing-platform"}
    )

    assert response.status_code == HTTPStatus.CONFLICT, response.text
    assert response.json()["reason"] == "platform-account-missing"
    assert response.json()["platform"] == "wolt"
    assert response.json()["courier_ids"] == [str(second.id)]
    async with session_module.session_factory() as session:
        accounts = (await session.scalars(select(CourierPlatformAccount))).all()
        assert len(accounts) == 5
        assert all(account.status is PlatformAccountStatus.PENDING for account in accounts)
        assert await session.get(IdempotencyKey, "missing-platform") is None


@pytest.mark.parametrize(("method", "path", "extra"), BULK_OPERATIONS)
async def test_bulk_key_is_required_and_cannot_be_reused_for_different_payload(
    client: AsyncClient, method: str, path: str, extra: dict[str, str]
) -> None:
    first, second = await seed_bulk_couriers()
    body = {"courier_ids": [str(first.id)], **extra}
    missing_key = await client.request(method, path, json=body)
    assert missing_key.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert missing_key.json()["header"] == "Idempotency-Key"
    assert (await client.get(f"/courier/{first.id}")).json()["platform_accounts"][0]["status"] == (
        "pending"
    )

    headers = {"Idempotency-Key": "bulk-key"}
    response = await client.request(method, path, json=body, headers=headers)
    assert response.status_code == HTTPStatus.OK, response.text
    mismatch = await client.request(
        method, path, json={"courier_ids": [str(second.id)], **extra}, headers=headers
    )
    assert mismatch.status_code == HTTPStatus.CONFLICT
    assert mismatch.json()["reason"] == "payload-mismatch"
    assert (await client.get(f"/courier/{second.id}")).json()["platform_accounts"][0]["status"] == (
        "pending"
    )

    unauthorized = await client.request(
        method, path, json=body, headers={**headers, "authorization": ""}
    )
    assert unauthorized.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize(("method", "path", "extra"), BULK_OPERATIONS)
async def test_bulk_flush_failure_rolls_back_rows_and_key(
    client: AsyncClient, method: str, path: str, extra: dict[str, str]
) -> None:
    couriers = await seed_bulk_couriers()
    body = {"courier_ids": [str(courier.id) for courier in couriers], **extra}
    headers = {"Idempotency-Key": "bulk-failure"}
    with failing_final_transaction():
        response = await client.request(method, path, json=body, headers=headers)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, response.text
    async with session_module.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Courier)) == 2
        accounts = (await session.scalars(select(CourierPlatformAccount))).all()
        assert len(accounts) == 6
        assert all(account.status is PlatformAccountStatus.PENDING for account in accounts)
        assert await session.get(IdempotencyKey, "bulk-failure") is None
    retry = await client.request(method, path, json=body, headers=headers)
    assert retry.status_code == HTTPStatus.OK, retry.text


@pytest.mark.parametrize(("method", "path", "extra"), BULK_OPERATIONS)
async def test_concurrent_bulk_requests_with_reversed_ids_are_atomic(
    client: AsyncClient, method: str, path: str, extra: dict[str, str]
) -> None:
    couriers = await seed_bulk_couriers(3)
    ids = [str(courier.id) for courier in couriers]
    async with asyncio.timeout(10):
        responses = await asyncio.gather(
            client.request(
                method,
                path,
                json={"courier_ids": ids, **extra},
                headers={"Idempotency-Key": "bulk-concurrent-first"},
            ),
            client.request(
                method,
                path,
                json={"courier_ids": ids[::-1], **extra},
                headers={"Idempotency-Key": "bulk-concurrent-second"},
            ),
        )

    if method == "POST":
        assert sorted(response.status_code for response in responses) == [200, 404]
        assert (await counts())[:3] == (0, 0, 0)
    else:
        assert [response.status_code for response in responses] == [200, 200]
        assert sorted(response.json()["updated_count"] for response in responses) == [0, 3]
        assert sorted(response.json()["unchanged_count"] for response in responses) == [0, 3]
        async with session_module.session_factory() as session:
            accounts = (await session.scalars(select(CourierPlatformAccount))).all()
        assert len(accounts) == 9
        for account in accounts:
            expected = (
                PlatformAccountStatus.ACTIVE
                if account.platform is DeliveryPlatform.WOLT
                else PlatformAccountStatus.PENDING
            )
            assert account.status is expected


async def test_physical_file_delete_cascades_document(client: AsyncClient) -> None:
    created = (await post_courier(client)).json()
    file_id = UUID(created["documents"][0]["file_id"])
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(File).where(File.id == file_id))

    assert await counts() == (1, 1, 0, 0, 0)


async def _retention_document(
    *,
    email: str,
    phone: str,
    purpose: DocumentPurpose,
    age_days: int,
    hold: datetime | None = None,
    reference: datetime | None = None,
) -> tuple[UUID, UUID]:
    """Создать ready File/Document нужного возраста напрямую в БД."""
    courier_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    created_at = (reference or datetime.now(tz=UTC)) - timedelta(days=age_days)
    async with session_module.session_factory() as session, session.begin():
        session.add(
            Courier(
                id=courier_id,
                full_name="Retention Courier",
                email=email,
                phone=phone,
                date_of_birth=datetime(1990, 1, 1, tzinfo=UTC).date(),
                consent_to_processing=False,
                consent_at=None,
            )
        )
        session.add(
            File(
                id=file_id,
                bucket="retention",
                key=str(file_id),
                original_name="retention.pdf",
                content_type="application/pdf",
                size=1,
                etag="etag",
                status=FileStatus.READY,
            )
        )
        session.add(
            CourierDocument(
                id=document_id,
                courier_id=courier_id,
                file_id=file_id,
                type=DocumentType.PASSPORT,
                purpose=purpose,
                legal_hold_until=hold,
            )
        )
        await session.flush()
        await session.execute(
            update(CourierDocument)
            .where(CourierDocument.id == document_id)
            .values(created_at=created_at)
        )
    return document_id, file_id


async def test_retention_boundaries_legal_hold_and_batch(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(tz=UTC)
    _eligible, eligible_file = await _retention_document(
        email="eligible@example.com",
        phone="+420700001001",
        purpose=DocumentPurpose.PLATFORM_ONBOARDING,
        age_days=90,
        reference=now,
    )
    young, young_file = await _retention_document(
        email="young@example.com",
        phone="+420700001002",
        purpose=DocumentPurpose.PLATFORM_ONBOARDING,
        age_days=89,
        reference=now,
    )
    held, held_file = await _retention_document(
        email="held@example.com",
        phone="+420700001003",
        purpose=DocumentPurpose.OTHER,
        age_days=400,
        hold=now + timedelta(days=1),
        reference=now,
    )
    _expired_hold, expired_file = await _retention_document(
        email="expired-hold@example.com",
        phone="+420700001004",
        purpose=DocumentPurpose.EMPLOYMENT_COMPLIANCE,
        age_days=1825,
        hold=now - timedelta(seconds=1),
        reference=now,
    )
    compliance_young, compliance_young_file = await _retention_document(
        email="compliance-young@example.com",
        phone="+420700001005",
        purpose=DocumentPurpose.EMPLOYMENT_COMPLIANCE,
        age_days=1824,
        reference=now,
    )
    _other_eligible, other_eligible_file = await _retention_document(
        email="other-eligible@example.com",
        phone="+420700001006",
        purpose=DocumentPurpose.OTHER,
        age_days=365,
        reference=now,
    )
    other_young, other_young_file = await _retention_document(
        email="other-young@example.com",
        phone="+420700001007",
        purpose=DocumentPurpose.OTHER,
        age_days=364,
        reference=now,
    )
    one_at_a_time = TEST_SETTINGS.model_copy(update={"retention_batch_size": 1})

    first = await purge_expired_documents(
        session_factory=sessions,
        settings=one_at_a_time,
        now=now,
    )
    second = await purge_expired_documents(
        session_factory=sessions,
        settings=TEST_SETTINGS,
        now=now,
    )

    assert (first, second) == (1, 2)
    async with session_module.session_factory() as session:
        remaining = set((await session.scalars(select(CourierDocument.id))).all())
        statuses = {row.id: row.status for row in (await session.scalars(select(File))).all()}
    assert remaining == {young, held, compliance_young, other_young}
    assert statuses[eligible_file] is FileStatus.DELETING
    assert statuses[expired_file] is FileStatus.DELETING
    assert statuses[other_eligible_file] is FileStatus.DELETING
    assert statuses[young_file] is FileStatus.READY
    assert statuses[held_file] is FileStatus.READY
    assert statuses[compliance_young_file] is FileStatus.READY
    assert statuses[other_young_file] is FileStatus.READY


async def test_upload_file_is_closed_on_natural_key_hit(
    client: AsyncClient,
    bucket: S3Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assert (await post_courier(client)).status_code == HTTPStatus.CREATED
    upload = UploadFile(filename="retry.png", file=io.BytesIO(b"unused"), headers=None)
    request = CourierAggregateCreate.model_validate(BASE_COURIER)
    async with storage(bucket) as objects:
        result = await create_courier_aggregate(
            request,
            [upload],
            session_factory=sessions,
            uploader=MultipartUploader(objects=objects, policy=POLICY),
            settings=TEST_SETTINGS,
        )

    assert not result.created
    assert upload.file.closed


def test_manifest_openapi_and_task_contract() -> None:
    app = build_app([courier_module])
    paths = app.openapi()["paths"]
    assert courier_module.router is not None
    route_auth = {
        (method, f"{courier_module.url_prefix}{route.path}"): is_authenticated(route.endpoint)
        for route in courier_module.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }

    assert courier_module.url_prefix == "/courier"
    assert courier_module.models == "app.modules.courier_module.models"
    assert courier_module.tasks == (retention_task,)
    assert getattr(retention_task, SCHEDULE_ATTR) == [{"cron": "29 2 * * *"}]
    assert task_name(courier_module, retention_task) == "courier_module.purge_expired_documents"
    assert route_auth == {
        ("POST", "/courier"): False,
        ("GET", "/courier"): True,
        ("POST", "/courier/bulk-delete"): True,
        ("PATCH", "/courier/bulk-status"): True,
        ("GET", "/courier/{courier_id}"): True,
        ("PATCH", "/courier/{courier_id}"): True,
        ("DELETE", "/courier/{courier_id}"): True,
        ("POST", "/courier/{courier_id}/platform-accounts"): True,
        ("PATCH", "/courier/{courier_id}/platform-accounts/{account_id}"): True,
        ("POST", "/courier/{courier_id}/documents"): True,
        ("PATCH", "/courier/{courier_id}/documents/{document_id}"): True,
        ("DELETE", "/courier/{courier_id}/documents/{document_id}"): True,
    }
    assert "200" in paths["/courier"]["post"]["responses"]
    idempotent_routes = {
        (method, f"{courier_module.url_prefix}{route.path}")
        for route in courier_module.router.routes
        if isinstance(route, APIRoute) and is_idempotent(route.endpoint)
        for method in route.methods or ()
    }
    assert idempotent_routes == {
        ("POST", "/courier/bulk-delete"),
        ("PATCH", "/courier/bulk-status"),
    }
    for method, path, _extra in BULK_OPERATIONS:
        operation = paths[path][method.lower()]
        assert "200" in operation["responses"]
        assert any(
            parameter["name"] == "Idempotency-Key"
            and parameter["in"] == "header"
            and parameter["required"]
            for parameter in operation["parameters"]
        )
    assert "/courier/{courier_id}/documents" not in {
        path for path, methods in paths.items() if "get" in methods
    }
    assert "/courier/{courier_id}/platform-accounts" not in {
        path for path, methods in paths.items() if "get" in methods
    }
