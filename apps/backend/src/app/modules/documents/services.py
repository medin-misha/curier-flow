"""Жизненный цикл шаблонов и оркестрация DB → S3 → DOCX."""

import asyncio
from dataclasses import dataclass
from pathlib import PurePath
from typing import NoReturn, cast
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, DependencyUnavailable, NotFound, ValidationFailed
from app.kernel.pagination import Page, PageParams
from app.modules.documents.docx import (
    DocxLimits,
    DocxTemplateError,
    extract_template_fields,
    render_template,
)
from app.modules.documents.models import DocumentTemplate
from app.modules.documents.schemas.requests import DocumentRenderRequest, DocumentTemplateCreate
from app.platform.files import File, FileStatus
from app.platform.s3 import ObjectStorage, ObjectTooLargeError

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentsSettings(BaseSettings):
    """Пределы безопасного разбора и заполнения DOCX."""

    model_config = SettingsConfigDict(
        env_prefix="documents_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_uncompressed_size: int = Field(default=104_857_600, gt=0)
    max_archive_entries: int = Field(default=2048, gt=0)
    max_fields: int = Field(default=200, gt=0)
    max_value_length: int = Field(default=10_000, gt=0)

    def docx_limits(self) -> DocxLimits:
        """Собрать неизменяемые лимиты чистого DOCX-рендерера."""
        return DocxLimits(
            max_uncompressed_size=self.max_uncompressed_size,
            max_archive_entries=self.max_archive_entries,
            max_fields=self.max_fields,
        )


documents_settings = DocumentsSettings()


@dataclass(frozen=True, slots=True)
class DocumentsRuntime:
    """Долгоживущий S3-клиент и лимиты модуля."""

    objects: ObjectStorage
    settings: DocumentsSettings


@dataclass(frozen=True, slots=True)
class TemplateCreation:
    """Результат natural-key создания с признаком новой строки."""

    template: DocumentTemplate
    created: bool


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """Готовые транзиентные байты и имя скачиваемого файла."""

    body: bytes
    name: str


async def create_template(
    request: DocumentTemplateCreate,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    runtime: DocumentsRuntime,
) -> TemplateCreation:
    """Проверить ready DOCX вне транзакции и сохранить извлечённую схему."""
    async with session_factory() as session:
        existing = await _template_by_file(request.file_id, session=session)
        if existing is not None:
            return _repeat_or_conflict(existing, request)
        file = await CRUD.get(File, request.file_id, session)

    file = _require_source(file, request.file_id)
    source = await _read_source(file, runtime=runtime)
    try:
        fields = await asyncio.to_thread(
            extract_template_fields,
            source,
            limits=runtime.settings.docx_limits(),
        )
    except DocxTemplateError as error:
        raise ValidationFailed(str(error), reason="invalid-docx-template") from error

    try:
        async with session_factory() as session, session.begin():
            template = await CRUD.create(DocumentTemplate, request, session, fields=fields)
        return TemplateCreation(template=template, created=True)
    except IntegrityError as error:
        constraint = _constraint_name(error)
        if constraint == "uq_document_templates_file_id":
            async with session_factory() as session:
                existing = await _template_by_file(request.file_id, session=session)
            if existing is not None:
                return _repeat_or_conflict(existing, request)
        _raise_known_integrity(error)


async def get_template(template_id: UUID, *, session: AsyncSession) -> DocumentTemplate:
    """Вернуть шаблон по идентификатору."""
    return await CRUD.get_or_404(DocumentTemplate, template_id, session)


async def list_templates(
    page: PageParams,
    *,
    session: AsyncSession,
) -> Page[DocumentTemplate]:
    """Вернуть keyset-страницу шаблонов."""
    return await CRUD.list_page(DocumentTemplate, session, page=page)


async def delete_template(template_id: UUID, *, session: AsyncSession) -> None:
    """Удалить шаблон, освободив исходный File для отдельного удаления."""
    template = await CRUD.get_or_404(DocumentTemplate, template_id, session)
    await CRUD.delete(template, session)


async def render_document(
    template_id: UUID,
    request: DocumentRenderRequest,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    runtime: DocumentsRuntime,
) -> RenderedDocument:
    """Прочитать шаблон и вернуть заполненный DOCX без сохранения результата."""
    async with session_factory() as session:
        row = (
            await session.execute(
                select(DocumentTemplate, File)
                .join(File, File.id == DocumentTemplate.file_id)
                .where(DocumentTemplate.id == template_id)
            )
        ).one_or_none()
    if row is None:
        raise NotFound(
            "DocumentTemplate not found",
            resource=DocumentTemplate.__name__,
            pk=str(template_id),
        )
    template, file = row._tuple()
    file = _require_source(file, template.file_id)
    values = _validate_values(
        template.fields,
        request.values,
        max_value_length=runtime.settings.max_value_length,
    )
    source = await _read_source(file, runtime=runtime)
    try:
        body = await asyncio.to_thread(
            render_template,
            source,
            values,
            limits=runtime.settings.docx_limits(),
        )
    except DocxTemplateError as error:
        raise Conflict(
            "Stored DOCX template can no longer be rendered",
            reason="broken-template-source",
        ) from error
    return RenderedDocument(body=body, name=template.name)


async def _template_by_file(
    file_id: UUID,
    *,
    session: AsyncSession,
) -> DocumentTemplate | None:
    """Найти natural-key шаблона по единственному исходному File."""
    return cast(
        DocumentTemplate | None,
        await session.scalar(select(DocumentTemplate).where(DocumentTemplate.file_id == file_id)),
    )


def _repeat_or_conflict(
    existing: DocumentTemplate,
    request: DocumentTemplateCreate,
) -> TemplateCreation:
    """Разрешить точный retry и отклонить переиспользование File."""
    if existing.name != request.name:
        raise Conflict(
            "File is already used by another document template",
            reason="template-file-in-use",
        )
    return TemplateCreation(template=existing, created=False)


def _require_source(file: File | None, file_id: UUID) -> File:
    """Разрешить только готовый File с каноническим DOCX MIME и суффиксом."""
    if file is None or file.status is FileStatus.DELETING:
        raise NotFound("File not found", resource=File.__name__, pk=str(file_id))
    if file.status is not FileStatus.READY:
        raise ValidationFailed("Template file is not ready", reason="file-not-ready")
    if file.content_type.lower() != DOCX_CONTENT_TYPE:
        raise ValidationFailed("Template file must be a DOCX", reason="invalid-template-type")
    if PurePath(file.original_name).suffix.lower() != ".docx":
        raise ValidationFailed(
            "Template filename must have a .docx suffix",
            reason="invalid-template-name",
        )
    return file


async def _read_source(file: File, *, runtime: DocumentsRuntime) -> bytes:
    """Скачать исходник с фактическим ограничением сохранённого размера."""
    try:
        downloaded = await runtime.objects.read_object(
            file.key,
            bucket=file.bucket,
            max_size=file.size,
        )
    except ObjectTooLargeError as error:
        raise Conflict(
            "Template source differs from confirmed File metadata",
            reason="template-source-changed",
        ) from error
    except (BotoCoreError, ClientError) as error:
        raise DependencyUnavailable("Object storage is unavailable") from error
    if downloaded is None:
        raise Conflict("Template source is missing", reason="template-source-missing")
    if downloaded.info.size != file.size or downloaded.info.etag != file.etag:
        raise Conflict(
            "Template source differs from confirmed File metadata",
            reason="template-source-changed",
        )
    return downloaded.body


def _validate_values(
    fields: dict[str, list[str]],
    provided: dict[str, dict[str, str]],
    *,
    max_value_length: int,
) -> dict[str, str]:
    """Потребовать точный набор полей и безопасные однострочные значения."""
    expected_paths = {f"{group}.{field}" for group, names in fields.items() for field in names}
    provided_paths = {f"{group}.{field}" for group, values in provided.items() for field in values}
    missing = sorted(expected_paths - provided_paths)
    unexpected = sorted(provided_paths - expected_paths)
    if missing or unexpected:
        raise ValidationFailed(
            "Render values do not match template fields",
            reason="field-mismatch",
            missing_fields=missing,
            unexpected_fields=unexpected,
        )

    flattened: dict[str, str] = {}
    invalid: list[str] = []
    for group, values in provided.items():
        for field, value in values.items():
            path = f"{group}.{field}"
            if len(value) > max_value_length or "\n" in value or "\r" in value:
                invalid.append(path)
            flattened[path] = value
    if invalid:
        raise ValidationFailed(
            "Render values must be bounded single-line strings",
            reason="invalid-field-values",
            fields=sorted(invalid),
        )
    return flattened


def _raise_known_integrity(error: IntegrityError) -> NoReturn:
    """Преобразовать DB-защиту File в стабильные публичные ошибки."""
    constraint = _constraint_name(error)
    if constraint == "document_template_file_not_ready":
        raise ValidationFailed("Template file is not ready", reason="file-not-ready") from error
    if constraint == "fk_document_templates_file_id_files":
        raise NotFound("File not found", resource=File.__name__) from error
    raise error


def _constraint_name(error: IntegrityError) -> str | None:
    """Достать имя PostgreSQL constraint из asyncpg adapter chain."""
    original = error.orig
    candidates = (
        original,
        original.__cause__ if original is not None else None,
        original.__context__ if original is not None else None,
    )
    for candidate in candidates:
        if candidate is None:
            continue
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name
        diag = getattr(candidate, "diag", None)
        name = getattr(diag, "constraint_name", None)
        if isinstance(name, str):
            return name
    return None
