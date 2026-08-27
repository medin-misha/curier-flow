"""Staging, потоковая загрузка и финализация platform File."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils.compat import uuid7

from app.kernel.context import actor_id
from app.kernel.errors import ValidationFailed
from app.kernel.events.bus import emit
from app.platform.files import (
    AsyncReadable,
    File,
    FileConfirmed,
    FileStatus,
    FileUploadStaging,
    MultipartUploader,
    StagingNotUploadedError,
    UploadRejectedError,
    create_file,
    create_staging,
    mark_staging_uploaded,
    record_multipart_upload_id,
)

_KEY_PREFIX = "courier-documents"
_MAX_FILENAME_LENGTH = 255

_logger = structlog.get_logger("app.modules.courier_module")


class DocumentUpload(AsyncReadable, Protocol):
    """Framework-neutral часть UploadFile, нужная сервису."""

    filename: str | None
    content_type: str | None

    async def close(self) -> None:
        """Закрыть спулированный multipart-файл."""
        ...


@dataclass(frozen=True, slots=True)
class PreparedUpload:
    """Проверенная до S3 metadata и durable id будущего File."""

    id: UUID
    bucket: str
    key: str
    original_name: str
    content_type: str
    source: DocumentUpload


@dataclass(slots=True)
class _UploadBudget:
    """Общий счётчик фактически прочитанных bytes multipart-запроса."""

    limit: int
    used: int = 0


@dataclass(frozen=True, slots=True)
class _BudgetedSource:
    """AsyncReadable, который применяет общий лимит поверх per-file policy."""

    source: AsyncReadable
    budget: _UploadBudget

    async def read(self, size: int) -> bytes:
        """Прочитать chunk и отвергнуть превышение aggregate limit."""
        chunk = await self.source.read(size)
        self.budget.used += len(chunk)
        if self.budget.used > self.budget.limit:
            raise UploadRejectedError("total_upload_too_large")
        return chunk


def prepare_uploads(
    uploads: Sequence[DocumentUpload],
    *,
    bucket: str,
    uploader: MultipartUploader,
) -> list[PreparedUpload]:
    """Проверить filename/MIME и назначить непрозрачные server keys."""
    prepared: list[PreparedUpload] = []
    for source in uploads:
        original_name = (source.filename or "").strip()
        if not original_name or len(original_name) > _MAX_FILENAME_LENGTH:
            raise ValidationFailed(
                "Document filename is required and must fit 255 characters",
                reason="invalid-filename",
            )
        content_type = uploader.policy.normalize_content_type(source.content_type or "")
        if not uploader.policy.allows_content_type(content_type):
            raise ValidationFailed(
                "Document content type is not allowed",
                reason="content-type-not-allowed",
            )
        file_id = uuid7()
        prepared.append(
            PreparedUpload(
                id=file_id,
                bucket=bucket,
                key=_build_key(file_id),
                original_name=original_name,
                content_type=content_type,
                source=source,
            )
        )
    return prepared


def _build_key(file_id: UUID) -> str:
    """Собрать безопасный object key без пользовательского filename."""
    today = datetime.now(tz=UTC)
    return f"{_KEY_PREFIX}/{today:%Y/%m/%d}/{file_id}"


async def create_staging_rows(
    uploads: Sequence[PreparedUpload],
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Durable-сохранить все будущие File ids до первого S3-вызова."""
    async with session_factory() as session, session.begin():
        for upload in uploads:
            await create_staging(
                session,
                file_id=upload.id,
                bucket=upload.bucket,
                key=upload.key,
                original_name=upload.original_name,
                content_type=upload.content_type,
            )


async def upload_all(
    uploads: Sequence[PreparedUpload],
    *,
    session_factory: async_sessionmaker[AsyncSession],
    uploader: MultipartUploader,
    total_limit: int,
) -> None:
    """Последовательно загрузить файлы с общим фактическим лимитом."""
    budget = _UploadBudget(limit=total_limit)
    for upload in uploads:

        async def remember_upload_id(upload_id: str, *, staging_id: UUID = upload.id) -> None:
            async with session_factory() as session, session.begin():
                recorded = await record_multipart_upload_id(session, staging_id, upload_id)
                if not recorded:
                    raise StagingNotUploadedError("uploading staging disappeared")

        try:
            result = await uploader.upload(
                _BudgetedSource(source=upload.source, budget=budget),
                bucket=upload.bucket,
                key=upload.key,
                content_type=upload.content_type,
                on_upload_created=remember_upload_id,
            )
        except UploadRejectedError as error:
            raise ValidationFailed(
                "Document upload rejected",
                reason=str(error),
            ) from error
        async with session_factory() as session, session.begin():
            recorded = await mark_staging_uploaded(
                session,
                upload.id,
                size=result.size,
                content_type=result.content_type,
                etag=result.etag,
            )
            if not recorded:
                raise StagingNotUploadedError("uploaded staging disappeared")


async def create_ready_file(
    staged: FileUploadStaging,
    *,
    session: AsyncSession,
) -> File:
    """Создать ready File и FileConfirmed в той же caller transaction."""
    if staged.size is None or staged.etag is None:
        raise StagingNotUploadedError("uploaded staging lacks result metadata")
    file = await create_file(
        session,
        file_id=staged.id,
        bucket=staged.bucket,
        key=staged.key,
        original_name=staged.original_name,
        content_type=staged.content_type,
        size=staged.size,
        status=FileStatus.READY,
        etag=staged.etag,
        owner_id=actor_id.get(),
    )
    emit(
        session,
        FileConfirmed(
            file_id=file.id,
            bucket=file.bucket,
            key=file.key,
            original_name=file.original_name,
            content_type=file.content_type,
            size=file.size,
            owner_id=file.owner_id,
        ),
    )
    return file


async def close_uploads(uploads: Sequence[DocumentUpload]) -> None:
    """Закрыть все UploadFile на каждой ветке, не раскрывая их имена в лог."""
    for upload in uploads:
        try:
            await upload.close()
        except Exception as error:
            _logger.warning(
                "courier.upload_close_failed",
                error=type(error).__name__,
            )
