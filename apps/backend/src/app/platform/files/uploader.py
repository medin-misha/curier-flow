"""Framework-neutral streaming multipart uploader для S3-compatible storage."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.platform.files.policy import FilePolicy
from app.platform.s3 import CompletedPart, ObjectStorage

MIN_MULTIPART_PART_SIZE = 5 * 1024 * 1024
MAX_MULTIPART_PART_SIZE = 5 * 1024 * 1024 * 1024
MAX_MULTIPART_PARTS = 10_000


class AsyncReadable(Protocol):
    """Минимальный async-интерфейс источника байтов без зависимости от FastAPI."""

    async def read(self, size: int) -> bytes:
        """Прочитать не более ``size`` байт; пустые bytes означают EOF."""
        ...


class UploadRejectedError(ValueError):
    """Загрузка нарушает общую файловую policy или multipart constraints."""


@dataclass(frozen=True, slots=True)
class UploadResult:
    """Фактические метаданные успешно завершённого multipart upload."""

    size: int
    content_type: str
    etag: str


@dataclass(frozen=True, slots=True)
class MultipartUploader:
    """Потоково загрузить AsyncReadable ограниченными частями в явный bucket."""

    objects: ObjectStorage
    policy: FilePolicy
    part_size: int = 8 * 1024 * 1024
    read_size: int = 1024 * 1024

    def __post_init__(self) -> None:
        """Проверить ограничения S3 до первого внешнего вызова."""
        if not MIN_MULTIPART_PART_SIZE <= self.part_size <= MAX_MULTIPART_PART_SIZE:
            raise ValueError("part_size is outside S3 multipart constraints")
        if not 0 < self.read_size <= self.part_size:
            raise ValueError("read_size must be positive and not exceed part_size")

    async def upload(
        self,
        source: AsyncReadable,
        *,
        bucket: str,
        key: str,
        content_type: str,
        on_upload_created: Callable[[str], Awaitable[None]],
    ) -> UploadResult:
        """Загрузить поток, durable-сохранить upload id callback-ом и вернуть metadata.

        Любое исключение, включая cancellation, запускает best-effort abort.
        Callback вызывается сразу после create multipart и до чтения bytes.
        """
        normalized_type = self.policy.normalize_content_type(content_type)
        if not self.policy.allows_content_type(normalized_type):
            raise UploadRejectedError("content_type_not_allowed")

        upload_id = await self.objects.create_multipart_upload(
            key,
            bucket=bucket,
            content_type=normalized_type,
        )
        try:
            await on_upload_created(upload_id)
            result = await self._upload_parts(
                source,
                bucket=bucket,
                key=key,
                upload_id=upload_id,
                content_type=normalized_type,
            )
        except BaseException:
            await self._best_effort_abort(bucket=bucket, key=key, upload_id=upload_id)
            raise
        return result

    async def _upload_parts(
        self,
        source: AsyncReadable,
        *,
        bucket: str,
        key: str,
        upload_id: str,
        content_type: str,
    ) -> UploadResult:
        """Собрать short reads в S3 parts и завершить multipart по порядку."""
        total = 0
        buffer = bytearray()
        parts: list[CompletedPart] = []
        eof = False
        while not eof:
            requested = min(self.read_size, self.part_size - len(buffer))
            chunk = await source.read(requested)
            if len(chunk) > requested:
                raise UploadRejectedError("source_returned_oversized_chunk")
            if not chunk:
                eof = True
                continue
            total += len(chunk)
            if total > self.policy.max_file_size:
                raise UploadRejectedError("file_too_large")
            buffer.extend(chunk)
            if len(buffer) == self.part_size:
                await self._append_part(parts, bytes(buffer), bucket, key, upload_id)
                buffer.clear()

        if not total:
            raise UploadRejectedError("empty_file")
        if buffer:
            await self._append_part(parts, bytes(buffer), bucket, key, upload_id)

        etag = await self.objects.complete_multipart_upload(
            key,
            upload_id,
            parts,
            bucket=bucket,
        )
        return UploadResult(size=total, content_type=content_type, etag=etag)

    async def _append_part(
        self,
        parts: list[CompletedPart],
        body: bytes,
        bucket: str,
        key: str,
        upload_id: str,
    ) -> None:
        """Отправить очередную part и сохранить её ETag с монотонным номером."""
        part_number = len(parts) + 1
        if part_number > MAX_MULTIPART_PARTS:
            raise UploadRejectedError("too_many_parts")
        etag = await self.objects.upload_part(
            key,
            upload_id,
            part_number,
            body,
            bucket=bucket,
        )
        parts.append(CompletedPart(part_number=part_number, etag=etag))

    async def _best_effort_abort(self, *, bucket: str, key: str, upload_id: str) -> None:
        """Попытаться abort даже при cancellation, не маскируя исходную ошибку."""
        abort = asyncio.create_task(
            self.objects.abort_multipart_upload(key, upload_id, bucket=bucket)
        )
        try:
            await asyncio.shield(abort)
        except BaseException:
            return
