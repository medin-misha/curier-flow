"""Общий file catalog, streaming uploader и durable staging cleanup."""

import asyncio
import importlib
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.db import session as session_module
from app.kernel.db.base import Base
from app.modules.storage import tasks as storage_tasks
from app.modules.storage.events import FileConfirmed as StorageFileConfirmed
from app.modules.storage.models import (
    File as StorageFile,
)
from app.modules.storage.models import (
    FileStatus as StorageFileStatus,
)
from app.modules.storage.models import (
    FileUploadStaging as StorageFileUploadStaging,
)
from app.modules.storage.models import (
    StagingStatus as StorageStagingStatus,
)
from app.modules.storage.services import cleanup_staged_uploads
from app.platform.files import (
    File,
    FileConfirmed,
    FilePolicy,
    FileStatus,
    FileUploadStaging,
    FileUploadStagingSettings,
    MultipartUploader,
    StagingNotUploadedError,
    StagingStatus,
    UploadRejectedError,
    claim_stale_staging,
    consume_uploaded_staging,
    create_file,
    create_staging,
    mark_staging_uploaded,
    record_multipart_upload_id,
    staging_settings,
)
from app.platform.files.uploader import MIN_MULTIPART_PART_SIZE
from app.platform.s3 import CompletedPart, ObjectStorage


def test_storage_imports_are_identity_reexports_of_the_single_platform_definitions() -> None:
    assert StorageFile is File
    assert StorageFileStatus is FileStatus
    assert StorageFileUploadStaging is FileUploadStaging
    assert StorageStagingStatus is StagingStatus
    assert StorageFileConfirmed is FileConfirmed
    assert Base.metadata.tables["files"] is File.__table__
    assert Base.metadata.tables["file_upload_staging"] is FileUploadStaging.__table__
    assert sum(mapper.class_.__name__ == "File" for mapper in Base.registry.mappers) == 1


def test_storage_model_package_makes_both_tables_visible_to_alembic_metadata() -> None:
    importlib.import_module("app.modules.storage.models")

    assert {"files", "file_upload_staging"} <= set(Base.metadata.tables)


async def test_catalog_participates_in_caller_rollback_and_never_commits(
    clean_db: None,  # noqa: ARG001
) -> None:
    factory = session_module.session_factory
    file_id = uuid4()
    async with factory() as session:
        transaction = await session.begin()
        await create_file(
            session,
            file_id=file_id,
            bucket="archive",
            key="aggregate/a",
            original_name="a.pdf",
            content_type="application/pdf",
            size=4,
            status=FileStatus.READY,
            etag="etag",
        )
        await transaction.rollback()

    async with factory() as session:
        assert await session.get(File, file_id) is None


async def test_staging_transitions_are_caller_owned_and_finalizer_consumes_only_uploaded(
    clean_db: None,  # noqa: ARG001
) -> None:
    factory = session_module.session_factory
    staging_id = uuid4()
    async with factory() as session, session.begin():
        await create_staging(
            session,
            file_id=staging_id,
            bucket="saved",
            key="aggregate/a",
            original_name="a.pdf",
            content_type="application/pdf",
        )

    with pytest.raises(StagingNotUploadedError):
        async with factory() as session, session.begin():
            await consume_uploaded_staging(session, [staging_id])

    async with factory() as session, session.begin():
        assert await record_multipart_upload_id(session, staging_id, "upload-1")
    async with factory() as session:
        row = await session.get(FileUploadStaging, staging_id)
        assert row is not None
        assert row.multipart_upload_id == "upload-1"

    async with factory() as session, session.begin():
        assert await mark_staging_uploaded(
            session,
            staging_id,
            size=4,
            content_type="application/pdf",
            etag="etag",
        )
    async with factory() as session, session.begin():
        rows = await consume_uploaded_staging(session, [staging_id])
        assert [row.id for row in rows] == [staging_id]

    async with factory() as session:
        assert await session.get(FileUploadStaging, staging_id) is None


class ChunkReader:
    """AsyncReadable с управляемыми short reads."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = deque(chunks)
        self.requests: list[int] = []

    async def read(self, size: int) -> bytes:
        self.requests.append(size)
        return self.chunks.popleft() if self.chunks else b""


@dataclass
class FakeMultipartObjects:
    """Минимальный in-memory двойник bucket-aware multipart primitives."""

    calls: list[tuple[Any, ...]] = field(default_factory=list)
    fail_part: bool = False

    async def create_multipart_upload(self, key: str, *, bucket: str, content_type: str) -> str:
        self.calls.append(("create", bucket, key, content_type))
        return "upload-1"

    async def upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        body: bytes,
        *,
        bucket: str,
    ) -> str:
        self.calls.append(("part", bucket, key, upload_id, part_number, len(body)))
        if self.fail_part:
            raise ConnectionError("part failed")
        return f"etag-{part_number}"

    async def complete_multipart_upload(
        self,
        key: str,
        upload_id: str,
        parts: list[CompletedPart],
        *,
        bucket: str,
    ) -> str:
        self.calls.append(
            ("complete", bucket, key, upload_id, [(part.part_number, part.etag) for part in parts])
        )
        return "final-etag"

    async def abort_multipart_upload(self, key: str, upload_id: str, *, bucket: str) -> None:
        self.calls.append(("abort", bucket, key, upload_id))


def uploader(objects: FakeMultipartObjects, *, limit: int) -> MultipartUploader:
    return MultipartUploader(
        objects=cast(ObjectStorage, objects),
        policy=FilePolicy(limit, frozenset({"application/pdf"})),
        part_size=MIN_MULTIPART_PART_SIZE,
        read_size=1024 * 1024,
    )


async def saved_upload_id(_upload_id: str) -> None:
    return None


async def test_uploader_coalesces_short_reads_limits_chunks_and_orders_etags() -> None:
    objects = FakeMultipartObjects()
    chunks = [b"a" * (512 * 1024) for _ in range(11)]
    reader = ChunkReader(chunks)

    result = await uploader(objects, limit=8 * 1024 * 1024).upload(
        reader,
        bucket="historic-bucket",
        key="aggregate/report",
        content_type=" Application/PDF ",
        on_upload_created=saved_upload_id,
    )

    assert result.size == 11 * 512 * 1024
    assert result.content_type == "application/pdf"
    assert result.etag == "final-etag"
    assert all(0 < requested <= 1024 * 1024 for requested in reader.requests)
    assert [call[-2] for call in objects.calls if call[0] == "part"] == [1, 2]
    assert objects.calls[-1][-1] == [(1, "etag-1"), (2, "etag-2")]
    assert {call[1] for call in objects.calls} == {"historic-bucket"}


@pytest.mark.parametrize(
    ("chunks", "limit", "reason"),
    [([], 10, "empty_file"), ([b"12345"], 4, "file_too_large")],
)
async def test_uploader_rejects_empty_and_oversize_and_aborts(
    chunks: list[bytes],
    limit: int,
    reason: str,
) -> None:
    objects = FakeMultipartObjects()

    with pytest.raises(UploadRejectedError, match=reason):
        await uploader(objects, limit=limit).upload(
            ChunkReader(chunks),
            bucket="saved",
            key="aggregate/a",
            content_type="application/pdf",
            on_upload_created=saved_upload_id,
        )

    assert objects.calls[-1] == ("abort", "saved", "aggregate/a", "upload-1")


async def test_uploader_saves_upload_id_before_reading_and_aborts_part_error() -> None:
    objects = FakeMultipartObjects(fail_part=True)
    order: list[str] = []

    class OrderedReader(ChunkReader):
        async def read(self, size: int) -> bytes:
            order.append("read")
            return await super().read(size)

    async def persist(upload_id: str) -> None:
        assert upload_id == "upload-1"
        order.append("persist")

    with pytest.raises(ConnectionError, match="part failed"):
        await uploader(objects, limit=MIN_MULTIPART_PART_SIZE).upload(
            OrderedReader([b"x" * (1024 * 1024) for _ in range(5)]),
            bucket="saved",
            key="aggregate/a",
            content_type="application/pdf",
            on_upload_created=persist,
        )

    assert order[0] == "persist"
    assert objects.calls[-1][0] == "abort"


async def test_uploader_best_effort_aborts_on_cancellation() -> None:
    objects = FakeMultipartObjects()
    reading = asyncio.Event()

    class BlockingReader:
        async def read(self, _size: int) -> bytes:
            reading.set()
            await asyncio.Event().wait()
            return b""

    task = asyncio.create_task(
        uploader(objects, limit=10).upload(
            BlockingReader(),
            bucket="saved",
            key="aggregate/a",
            content_type="application/pdf",
            on_upload_created=saved_upload_id,
        )
    )
    await reading.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert objects.calls[-1][0] == "abort"


async def test_s3_bucket_override_and_exact_key_crash_fallback() -> None:
    client = AsyncMock()
    client.list_multipart_uploads.return_value = {
        "Uploads": [
            {"Key": "aggregate/a", "UploadId": "exact"},
            {"Key": "aggregate/a-copy", "UploadId": "prefix-only"},
        ]
    }
    objects = ObjectStorage(client=client, signer=client, bucket="configured", presign_ttl=900)

    await objects.abort_multipart_uploads_for_key("aggregate/a", bucket="saved")
    await objects.delete_object("aggregate/a", bucket="saved")

    client.list_multipart_uploads.assert_awaited_once_with(Bucket="saved", Prefix="aggregate/a")
    client.abort_multipart_upload.assert_awaited_once_with(
        Bucket="saved", Key="aggregate/a", UploadId="exact"
    )
    client.delete_object.assert_awaited_once_with(Bucket="saved", Key="aggregate/a")


async def test_crash_fallback_paginates_all_exact_key_uploads() -> None:
    client = AsyncMock()
    client.list_multipart_uploads.side_effect = [
        {
            "Uploads": [{"Key": "aggregate/a", "UploadId": "first"}],
            "IsTruncated": True,
            "NextKeyMarker": "aggregate/a",
            "NextUploadIdMarker": "first",
        },
        {
            "Uploads": [
                {"Key": "aggregate/a", "UploadId": "second"},
                {"Key": "aggregate/a-copy", "UploadId": "prefix-only"},
            ],
            "IsTruncated": False,
        },
    ]
    objects = ObjectStorage(client=client, signer=client, bucket="configured", presign_ttl=900)

    await objects.abort_multipart_uploads_for_key("aggregate/a", bucket="saved")

    assert [call.kwargs["UploadId"] for call in client.abort_multipart_upload.await_args_list] == [
        "first",
        "second",
    ]


@dataclass
class FakeCleanupObjects:
    """S3 cleanup двойник с failure isolation и проверяемым порядком."""

    fail_delete: set[str] = field(default_factory=set)
    fail_abort: set[str] = field(default_factory=set)
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    before_delete: Callable[[str], Awaitable[None]] | None = None

    async def abort_multipart_upload(
        self,
        key: str,
        _upload_id: str,
        *,
        bucket: str,
    ) -> None:
        self.calls.append(("abort-id", bucket, key))
        if key in self.fail_abort:
            raise ConnectionError("abort failed")

    async def abort_multipart_uploads_for_key(self, key: str, *, bucket: str) -> None:
        self.calls.append(("abort-fallback", bucket, key))
        if key in self.fail_abort:
            raise ConnectionError("abort failed")

    async def delete_object(self, key: str, *, bucket: str) -> None:
        if self.before_delete is not None:
            await self.before_delete(key)
        self.calls.append(("delete", bucket, key))
        if key in self.fail_delete:
            raise ConnectionError("delete failed")


async def add_staging(
    factory: async_sessionmaker[AsyncSession],
    *,
    key: str,
    status: StagingStatus,
    age: timedelta,
    upload_id: str | None = None,
    claimed_until: datetime | None = None,
) -> UUID:
    row_id = uuid4()
    moment = datetime.now(tz=UTC) - age
    async with factory() as session, session.begin():
        session.add(
            FileUploadStaging(
                id=row_id,
                bucket="saved-bucket",
                key=key,
                status=status,
                original_name="never-log-me.pdf",
                content_type="application/pdf",
                multipart_upload_id=upload_id,
                cleanup_claim_token=uuid4() if status is StagingStatus.DELETING else None,
                cleanup_claimed_until=claimed_until,
                created_at=moment,
                updated_at=moment,
            )
        )
    return row_id


def cleanup_settings(*, batch_size: int = 100) -> FileUploadStagingSettings:
    return FileUploadStagingSettings(ttl=60, claim_ttl=30, batch_size=batch_size)


@pytest.mark.parametrize("status", [StagingStatus.UPLOADING, StagingStatus.UPLOADED])
async def test_cleanup_removes_stale_uploading_and_uploaded(
    clean_db: None,  # noqa: ARG001
    status: StagingStatus,
) -> None:
    factory = session_module.session_factory
    row_id = await add_staging(
        factory,
        key=f"aggregate/{status.value}",
        status=status,
        age=timedelta(minutes=2),
        upload_id="known" if status is StagingStatus.UPLOADING else None,
    )
    objects = FakeCleanupObjects()

    cleaned = await cleanup_staged_uploads(
        session_factory=factory,
        objects=cast(ObjectStorage, objects),
        settings=cleanup_settings(),
    )

    assert cleaned == 1
    async with factory() as session:
        assert await session.get(FileUploadStaging, row_id) is None
    assert objects.calls[-1] == ("delete", "saved-bucket", f"aggregate/{status.value}")


async def test_cleanup_recovers_expired_deleting_but_skips_active_lease(
    clean_db: None,  # noqa: ARG001
) -> None:
    factory = session_module.session_factory
    now = datetime.now(tz=UTC)
    expired = await add_staging(
        factory,
        key="aggregate/expired",
        status=StagingStatus.DELETING,
        age=timedelta(minutes=2),
        claimed_until=now - timedelta(seconds=1),
    )
    active = await add_staging(
        factory,
        key="aggregate/active",
        status=StagingStatus.DELETING,
        age=timedelta(minutes=2),
        claimed_until=now + timedelta(minutes=2),
    )

    assert (
        await cleanup_staged_uploads(
            session_factory=factory,
            objects=cast(ObjectStorage, FakeCleanupObjects()),
            settings=cleanup_settings(),
        )
        == 1
    )
    async with factory() as session:
        assert await session.get(FileUploadStaging, expired) is None
        assert await session.get(FileUploadStaging, active) is not None


async def test_claim_lease_prevents_parallel_take_and_retries_after_expiry(
    clean_db: None,  # noqa: ARG001
) -> None:
    factory = session_module.session_factory
    await add_staging(
        factory,
        key="aggregate/leased",
        status=StagingStatus.UPLOADING,
        age=timedelta(minutes=2),
    )
    now = datetime.now(tz=UTC)
    async with factory() as session, session.begin():
        first = await claim_stale_staging(
            session,
            stale_before=now - timedelta(minutes=1),
            now=now,
            lease=timedelta(seconds=30),
            limit=10,
        )
    async with factory() as session, session.begin():
        second = await claim_stale_staging(
            session,
            stale_before=now - timedelta(minutes=1),
            now=now,
            lease=timedelta(seconds=30),
            limit=10,
        )
    async with factory() as session, session.begin():
        await session.execute(
            update(FileUploadStaging).values(cleanup_claimed_until=now - timedelta(seconds=1))
        )
    async with factory() as session, session.begin():
        retried = await claim_stale_staging(
            session,
            stale_before=now - timedelta(minutes=1),
            now=now,
            lease=timedelta(seconds=30),
            limit=10,
        )

    assert len(first) == 1
    assert second == []
    assert len(retried) == 1
    assert retried[0].token != first[0].token


async def test_cleanup_deletes_s3_before_row_and_missing_object_is_success(
    clean_db: None,  # noqa: ARG001
) -> None:
    factory = session_module.session_factory
    row_id = await add_staging(
        factory,
        key="aggregate/missing",
        status=StagingStatus.UPLOADED,
        age=timedelta(minutes=2),
    )
    present_during_s3: list[bool] = []

    async def assert_row_present(_key: str) -> None:
        async with factory() as session:
            present_during_s3.append(await session.get(FileUploadStaging, row_id) is not None)

    objects = FakeCleanupObjects(before_delete=assert_row_present)
    assert (
        await cleanup_staged_uploads(
            session_factory=factory,
            objects=cast(ObjectStorage, objects),
            settings=cleanup_settings(),
        )
        == 1
    )
    assert present_during_s3 == [True]
    async with factory() as session:
        assert await session.get(FileUploadStaging, row_id) is None


async def test_cleanup_failure_isolation_keeps_reason_code_and_honors_batch_limit(
    clean_db: None,  # noqa: ARG001
) -> None:
    factory = session_module.session_factory
    broken = await add_staging(
        factory,
        key="aggregate/broken",
        status=StagingStatus.UPLOADED,
        age=timedelta(minutes=3),
    )
    await add_staging(
        factory,
        key="aggregate/healthy",
        status=StagingStatus.UPLOADED,
        age=timedelta(minutes=2),
    )
    await add_staging(
        factory,
        key="aggregate/deferred",
        status=StagingStatus.UPLOADED,
        age=timedelta(minutes=1, seconds=30),
    )
    objects = FakeCleanupObjects(fail_delete={"aggregate/broken"})

    cleaned = await cleanup_staged_uploads(
        session_factory=factory,
        objects=cast(ObjectStorage, objects),
        settings=cleanup_settings(batch_size=2),
    )

    assert cleaned == 1
    async with factory() as session:
        broken_row = await session.get(FileUploadStaging, broken)
        assert broken_row is not None
        assert broken_row.status is StagingStatus.DELETING
        assert broken_row.last_error == "object_delete_failed"
        assert await session.scalar(select(func.count()).select_from(FileUploadStaging)) == 2


async def test_cleanup_task_owns_client_settings_and_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    objects = object()
    cleanup = AsyncMock(return_value=7)

    @asynccontextmanager
    async def owned_client(_settings: object) -> AsyncIterator[object]:
        yield objects

    monkeypatch.setattr(storage_tasks, "storage", owned_client)
    monkeypatch.setattr(storage_tasks, "cleanup_staged_uploads", cleanup)

    assert await storage_tasks.cleanup_file_upload_staging() == 7
    cleanup.assert_awaited_once_with(
        session_factory=session_module.session_factory,
        objects=objects,
        settings=staging_settings,
    )
