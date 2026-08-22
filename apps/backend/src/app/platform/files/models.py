"""ORM-модели общего каталога файлов и durable upload staging."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class FileStatus(StrEnum):
    """Состояние файла в общем однонаправленном lifecycle."""

    PENDING = "pending"
    READY = "ready"
    DELETING = "deleting"


class StagingStatus(StrEnum):
    """Состояние durable staging-загрузки до создания доменного File."""

    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    DELETING = "deleting"


def _enum_values(enum: type[StrEnum]) -> list[str]:
    """Вернуть значения строкового enum для хранения в VARCHAR."""
    return [member.value for member in enum]


class File(UUIDPkMixin, TimestampMixin, Base):
    """Метаданные S3-объекта без содержимого и бизнес-владельца."""

    __tablename__ = "files"
    __patchable__ = frozenset()
    __table_args__ = (
        Index("ix_files_status_created_at", "status", "created_at"),
        UniqueConstraint("bucket", "key"),
    )

    bucket: Mapped[str] = mapped_column(String(63))
    key: Mapped[str] = mapped_column(String(1024))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    etag: Mapped[str | None] = mapped_column(String(128), default=None)
    status: Mapped[FileStatus] = mapped_column(
        Enum(
            FileStatus,
            name="file_status",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
        ),
        default=FileStatus.PENDING,
    )
    owner_id: Mapped[UUID | None] = mapped_column(default=None)


Index("ix_files_keyset", File.created_at.desc(), File.id.desc())


class FileUploadStaging(UUIDPkMixin, TimestampMixin, Base):
    """Durable адрес и состояние S3 upload до атомарного создания File."""

    __tablename__ = "file_upload_staging"
    __patchable__ = frozenset()
    __table_args__ = (
        UniqueConstraint("bucket", "key"),
        Index("ix_file_upload_staging_status_updated_at", "status", "updated_at"),
        Index(
            "ix_file_upload_staging_deleting_lease",
            "status",
            "cleanup_claimed_until",
            "updated_at",
        ),
    )

    bucket: Mapped[str] = mapped_column(String(63))
    key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[StagingStatus] = mapped_column(
        Enum(
            StagingStatus,
            name="staging_status",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
        ),
        default=StagingStatus.UPLOADING,
    )
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255))
    size: Mapped[int | None] = mapped_column(BigInteger, default=None)
    etag: Mapped[str | None] = mapped_column(String(128), default=None)
    multipart_upload_id: Mapped[str | None] = mapped_column(String(1024), default=None)
    cleanup_claim_token: Mapped[UUID | None] = mapped_column(default=None)
    cleanup_claimed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    last_error: Mapped[str | None] = mapped_column(String(64), default=None)
