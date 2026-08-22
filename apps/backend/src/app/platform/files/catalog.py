"""DB-only операции общего каталога File и durable staging.

Функции принимают существующий ``AsyncSession`` и намеренно не открывают и не
коммитят транзакции, не выполняют внешний I/O и не пишут события. Границу
атомарности и ``emit(FileConfirmed)`` всегда задаёт caller.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.files.models import File, FileStatus, FileUploadStaging, StagingStatus


class StagingNotUploadedError(RuntimeError):
    """Finalizer попытался поглотить отсутствующий или не uploaded staging."""


@dataclass(frozen=True, slots=True)
class StagingCleanupClaim:
    """Снимок claim, достаточный для S3 cleanup после закрытия транзакции."""

    id: UUID
    bucket: str
    key: str
    multipart_upload_id: str | None
    token: UUID


async def create_file(
    session: AsyncSession,
    *,
    file_id: UUID,
    bucket: str,
    key: str,
    original_name: str,
    content_type: str,
    size: int,
    status: FileStatus = FileStatus.PENDING,
    etag: str | None = None,
    owner_id: UUID | None = None,
) -> File:
    """Добавить File в caller transaction и flush-нуть сгенерированные поля."""
    file = File(
        id=file_id,
        bucket=bucket,
        key=key,
        original_name=original_name,
        content_type=content_type,
        size=size,
        status=status,
        etag=etag,
        owner_id=owner_id,
    )
    session.add(file)
    await session.flush()
    return file


async def get_file(
    session: AsyncSession, file_id: UUID, *, for_update: bool = False
) -> File | None:
    """Получить File по id, при необходимости заблокировав строку."""
    statement = select(File).where(File.id == file_id)
    if for_update:
        statement = statement.with_for_update()
    return cast(File | None, await session.scalar(statement))


async def mark_file_ready(
    session: AsyncSession, file_id: UUID, *, etag: str
) -> tuple[File | None, bool]:
    """Перевести pending File в ready без emit и вернуть признак перехода."""
    file = await get_file(session, file_id, for_update=True)
    if file is None or file.status is FileStatus.DELETING:
        return file, False
    if file.status is FileStatus.READY:
        return file, False
    file.status = FileStatus.READY
    file.etag = etag
    await session.flush()
    return file, True


async def mark_file_deleting(session: AsyncSession, file_id: UUID) -> File | None:
    """Однонаправленно перевести существующий File в deleting."""
    file = await get_file(session, file_id, for_update=True)
    if file is not None:
        file.status = FileStatus.DELETING
        await session.flush()
    return file


async def create_staging(
    session: AsyncSession,
    *,
    file_id: UUID,
    bucket: str,
    key: str,
    original_name: str,
    content_type: str,
) -> FileUploadStaging:
    """Создать durable uploading staging внутри caller transaction."""
    row = FileUploadStaging(
        id=file_id,
        bucket=bucket,
        key=key,
        original_name=original_name,
        content_type=content_type,
        status=StagingStatus.UPLOADING,
    )
    session.add(row)
    await session.flush()
    return row


async def record_multipart_upload_id(
    session: AsyncSession,
    staging_id: UUID,
    upload_id: str,
) -> bool:
    """Сохранить upload id, только пока staging остаётся uploading."""
    changed_id = await session.scalar(
        update(FileUploadStaging)
        .where(
            FileUploadStaging.id == staging_id,
            FileUploadStaging.status == StagingStatus.UPLOADING,
        )
        .values(multipart_upload_id=upload_id)
        .returning(FileUploadStaging.id)
    )
    return changed_id is not None


async def mark_staging_uploaded(
    session: AsyncSession,
    staging_id: UUID,
    *,
    size: int,
    content_type: str,
    etag: str,
) -> bool:
    """Условно выполнить uploading -> uploaded в caller transaction."""
    changed_id = await session.scalar(
        update(FileUploadStaging)
        .where(
            FileUploadStaging.id == staging_id,
            FileUploadStaging.status == StagingStatus.UPLOADING,
        )
        .values(
            status=StagingStatus.UPLOADED,
            size=size,
            content_type=content_type,
            etag=etag,
            multipart_upload_id=None,
            last_error=None,
        )
        .returning(FileUploadStaging.id)
    )
    return changed_id is not None


async def consume_uploaded_staging(
    session: AsyncSession,
    staging_ids: Sequence[UUID],
) -> list[FileUploadStaging]:
    """Заблокировать и удалить только полный набор uploaded staging rows."""
    expected = sorted(set(staging_ids), key=str)
    rows = list(
        (
            await session.scalars(
                select(FileUploadStaging)
                .where(FileUploadStaging.id.in_(expected))
                .order_by(FileUploadStaging.id)
                .with_for_update()
            )
        ).all()
    )
    if len(rows) != len(expected) or any(row.status is not StagingStatus.UPLOADED for row in rows):
        raise StagingNotUploadedError("staging rows must all exist in uploaded state")
    for row in rows:
        await session.delete(row)
    await session.flush()
    return rows


async def claim_stale_staging(
    session: AsyncSession,
    *,
    stale_before: datetime,
    now: datetime,
    lease: timedelta,
    limit: int,
) -> list[StagingCleanupClaim]:
    """Claim stale rows через SKIP LOCKED и записать отдельный lease token."""
    stale_upload = FileUploadStaging.status.in_(
        (StagingStatus.UPLOADING, StagingStatus.UPLOADED)
    ) & (FileUploadStaging.updated_at < stale_before)
    expired_claim = (FileUploadStaging.status == StagingStatus.DELETING) & or_(
        FileUploadStaging.cleanup_claimed_until.is_(None),
        FileUploadStaging.cleanup_claimed_until <= now,
    )
    rows = list(
        (
            await session.scalars(
                select(FileUploadStaging)
                .where(or_(stale_upload, expired_claim))
                .order_by(FileUploadStaging.updated_at, FileUploadStaging.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    claimed: list[StagingCleanupClaim] = []
    for row in rows:
        token = uuid4()
        row.status = StagingStatus.DELETING
        row.cleanup_claim_token = token
        row.cleanup_claimed_until = now + lease
        claimed.append(
            StagingCleanupClaim(
                id=row.id,
                bucket=row.bucket,
                key=row.key,
                multipart_upload_id=row.multipart_upload_id,
                token=token,
            )
        )
    await session.flush()
    return claimed


async def delete_claimed_staging(session: AsyncSession, claim: StagingCleanupClaim) -> bool:
    """Удалить staging только если caller всё ещё владеет тем же lease token."""
    deleted_id = await session.scalar(
        delete(FileUploadStaging)
        .where(
            FileUploadStaging.id == claim.id,
            FileUploadStaging.cleanup_claim_token == claim.token,
            FileUploadStaging.status == StagingStatus.DELETING,
        )
        .returning(FileUploadStaging.id)
    )
    return deleted_id is not None


async def record_cleanup_error(
    session: AsyncSession,
    claim: StagingCleanupClaim,
    *,
    reason_code: str,
) -> bool:
    """Записать короткий безопасный reason code при сохранении lease row."""
    changed_id = await session.scalar(
        update(FileUploadStaging)
        .where(
            FileUploadStaging.id == claim.id,
            FileUploadStaging.cleanup_claim_token == claim.token,
            FileUploadStaging.status == StagingStatus.DELETING,
        )
        .values(last_error=reason_code[:64])
        .returning(FileUploadStaging.id)
    )
    return changed_id is not None
