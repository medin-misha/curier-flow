"""Таблица `document_templates`: неизменяемые DOCX-шаблоны."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class DocumentTemplate(UUIDPkMixin, TimestampMixin, Base):
    """Именованный шаблон со схемой полей и исходным File."""

    __tablename__ = "document_templates"
    __patchable__ = frozenset()
    __table_args__ = (
        UniqueConstraint("file_id"),
        CheckConstraint(
            "char_length(btrim(name)) > 0 AND name = btrim(name)",
            name="name_trimmed",
        ),
        CheckConstraint("jsonb_typeof(fields) = 'object'", name="fields_object"),
    )

    name: Mapped[str] = mapped_column(String(255))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    fields: Mapped[dict[str, list[str]]] = mapped_column(JSONB)


Index(
    "ix_document_templates_keyset",
    DocumentTemplate.created_at.desc(),
    DocumentTemplate.id.desc(),
)
