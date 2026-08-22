"""Таблица `courier_documents`: документы aggregate курьера."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin
from app.platform.files import File

if TYPE_CHECKING:
    from app.modules.courier_module.models.courier import Courier


class DocumentType(StrEnum):
    """Тип удостоверяющего или разрешительного документа."""

    PASSPORT = "passport"
    IDENTITY_CARD = "identity_card"
    RESIDENCE_PERMIT = "residence_permit"
    WORK_PERMIT = "work_permit"
    DRIVING_LICENSE = "driving_license"
    OTHER = "other"


class DocumentPurpose(StrEnum):
    """Бизнес-цель хранения документа, определяющая retention."""

    PLATFORM_ONBOARDING = "platform_onboarding"
    EMPLOYMENT_COMPLIANCE = "employment_compliance"
    OTHER = "other"


def _enum_values(enum: type[StrEnum]) -> list[str]:
    """Вернуть строковые значения enum для VARCHAR-колонки."""
    return [member.value for member in enum]


class CourierDocument(UUIDPkMixin, TimestampMixin, Base):
    """Metadata документа и однонаправленная ссылка на общий File."""

    __tablename__ = "courier_documents"
    __patchable__ = frozenset({"type", "purpose", "legal_hold_until"})
    __table_args__ = (UniqueConstraint("file_id"),)

    courier_id: Mapped[UUID] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    purpose: Mapped[DocumentPurpose] = mapped_column(
        Enum(
            DocumentPurpose,
            name="document_purpose",
            native_enum=False,
            length=32,
            values_callable=_enum_values,
        ),
        index=True,
    )
    legal_hold_until: Mapped[datetime | None] = mapped_column(default=None, index=True)
    type: Mapped[DocumentType] = mapped_column(
        Enum(
            DocumentType,
            name="document_type",
            native_enum=False,
            length=32,
            values_callable=_enum_values,
        ),
        index=True,
    )

    courier: Mapped["Courier"] = relationship(back_populates="documents")
    file: Mapped[File] = relationship(lazy="joined", passive_deletes=True)


Index(
    "ix_courier_documents_keyset",
    CourierDocument.created_at.desc(),
    CourierDocument.id.desc(),
)
Index(
    "ix_courier_documents_courier_keyset",
    CourierDocument.courier_id,
    CourierDocument.created_at.desc(),
    CourierDocument.id.desc(),
)
Index(
    "ix_courier_documents_retention",
    CourierDocument.type,
    CourierDocument.purpose,
    CourierDocument.created_at,
)
