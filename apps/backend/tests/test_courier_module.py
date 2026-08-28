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
from app.kernel.db import session as session_module
from app.kernel.events.models import OutboxMessage
from app.kernel.security.authentication import is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.courier_module import handlers as courier_handlers
from app.modules.courier_module.models import (
    Courier,
    CourierDocument,
    CourierPlatformAccount,
    DocumentPurpose,
    DocumentType,
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


@dataclass
class TransactionWatch:
    """Все синхронные Session, открывавшие транзакцию в текущем тесте."""

    sessions: list[Session] = field(default_factory=list)

    def open_now(self) -> list[Session]:
        """Вернуть сессии с открытой транзакцией прямо сейчас."""
        return [session for session in self.sessions if session.in_transaction()]


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
        watch.sessions.append(session)

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
    assert "/courier/{courier_id}/documents" not in {
        path for path, methods in paths.items() if "get" in methods
    }
    assert "/courier/{courier_id}/platform-accounts" not in {
        path for path, methods in paths.items() if "get" in methods
    }
