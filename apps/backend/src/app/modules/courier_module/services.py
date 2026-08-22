"""Бизнес-логика courier aggregate, staged uploads и retention."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn, Protocol, cast
from uuid import UUID

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import and_, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.base import ExecutableOption
from uuid_utils.compat import uuid7

from app.kernel.context import actor_id
from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, NotFound, ValidationFailed
from app.kernel.events.bus import emit
from app.kernel.pagination import Page, PageParams, decode_cursor, encode_cursor
from app.modules.courier_module.models import (
    Courier,
    CourierDocument,
    CourierPlatformAccount,
    DocumentPurpose,
    DocumentType,
    PlatformAccountStatus,
)
from app.modules.courier_module.schemas.requests import (
    CourierAggregateCreate,
    CourierDocumentCreate,
    CourierDocumentPatch,
    CourierPatch,
    PlatformAccountCreate,
    PlatformAccountPatch,
)
from app.platform.files import (
    AsyncReadable,
    File,
    FileConfirmed,
    FileStatus,
    FileUploadStaging,
    MultipartUploader,
    StagingNotUploadedError,
    StagingStatus,
    UploadRejectedError,
    consume_uploaded_staging,
    create_file,
    create_staging,
    mark_file_deleting,
    mark_staging_uploaded,
    record_multipart_upload_id,
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
_PHONE_FORMATTING = str.maketrans("", "", " -()")
_KEY_PREFIX = "courier-documents"
_MAX_EMAIL_LENGTH = 320
_MAX_FILENAME_LENGTH = 255

_logger = structlog.get_logger("app.modules.courier_module")


class CourierModuleSettings(BaseSettings):
    """Upload limits, retention policy и расписание courier_module."""

    model_config = SettingsConfigDict(
        env_prefix="courier_module_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_documents: int = Field(default=20, ge=0)
    max_total_upload_size: int = Field(default=104_857_600, gt=0)
    retention_platform_onboarding_days: int = Field(default=90, ge=1)
    retention_employment_compliance_days: int = Field(default=1825, ge=1)
    retention_other_days: int = Field(default=365, ge=1)
    retention_cron: str = "29 2 * * *"
    retention_batch_size: int = Field(default=100, ge=1)


courier_module_settings = CourierModuleSettings()


class DocumentUpload(AsyncReadable, Protocol):
    """Framework-neutral часть UploadFile, нужная сервису."""

    filename: str | None
    content_type: str | None

    async def close(self) -> None:
        """Закрыть спулированный multipart-файл."""
        ...


@dataclass(frozen=True, slots=True)
class AggregateCreateResult:
    """Courier aggregate и признак фактического создания."""

    courier: Courier
    created: bool


@dataclass(frozen=True, slots=True)
class _PreparedUpload:
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


def normalize_email(value: str) -> str:
    """Нормализовать и проверить email natural key."""
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > _MAX_EMAIL_LENGTH
        or _EMAIL.fullmatch(normalized) is None
    ):
        raise ValidationFailed("Invalid email", reason="invalid-email")
    return normalized


def normalize_phone(value: str) -> str:
    """Убрать разрешённое форматирование и проверить строгий E.164."""
    normalized = value.translate(_PHONE_FORMATTING)
    if _PHONE.fullmatch(normalized) is None:
        raise ValidationFailed("Invalid phone", reason="invalid-phone")
    return normalized


async def create_courier_aggregate(
    request: CourierAggregateCreate,
    uploads: Sequence[DocumentUpload],
    *,
    session_factory: async_sessionmaker[AsyncSession],
    uploader: MultipartUploader,
    settings: CourierModuleSettings,
) -> AggregateCreateResult:
    """Естественно идемпотентно создать Courier и все дочерние строки.

    До S3 выполняется только короткое чтение и отдельный commit staging. Все
    сетевые вызовы идут без открытой DB-транзакции. Финальная транзакция либо
    создаёт Courier, accounts, Documents, ready Files и outbox целиком, либо
    не создаёт ни одной доменной строки.
    """
    normalized = request.model_copy(
        update={
            "email": normalize_email(request.email),
            "phone": normalize_phone(request.phone),
        }
    )
    try:
        _validate_upload_count(normalized.documents, uploads, settings=settings)
        existing = await _find_by_identity(
            normalized.email,
            normalized.phone,
            session_factory=session_factory,
        )
        if existing is not None:
            return AggregateCreateResult(courier=existing, created=False)

        prepared = _prepare_uploads(
            uploads,
            bucket=uploader.objects.bucket,
            uploader=uploader,
        )
        await _create_staging_rows(prepared, session_factory=session_factory)
        await _upload_all(
            prepared,
            session_factory=session_factory,
            uploader=uploader,
            total_limit=settings.max_total_upload_size,
        )
        inserted = await _finalize_new_aggregate(
            normalized,
            prepared,
            session_factory=session_factory,
        )
        if inserted:
            courier = await _load_courier_by_identity(
                normalized.email,
                normalized.phone,
                session_factory=session_factory,
            )
            return AggregateCreateResult(courier=courier, created=True)

        winner = await _find_by_identity(
            normalized.email,
            normalized.phone,
            session_factory=session_factory,
        )
        if winner is None:
            raise Conflict("Courier identity changed concurrently", reason="identity-conflict")
        return AggregateCreateResult(courier=winner, created=False)
    finally:
        await _close_uploads(uploads)


async def create_courier_document(
    courier_id: UUID,
    request: CourierDocumentCreate,
    upload: DocumentUpload,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    uploader: MultipartUploader,
    settings: CourierModuleSettings,
) -> CourierDocument:
    """Потоково загрузить один File и атомарно создать CourierDocument."""
    try:
        async with session_factory() as session:
            await _require_courier(courier_id, session=session)

        prepared = _prepare_uploads(
            [upload],
            bucket=uploader.objects.bucket,
            uploader=uploader,
        )
        await _create_staging_rows(prepared, session_factory=session_factory)
        await _upload_all(
            prepared,
            session_factory=session_factory,
            uploader=uploader,
            total_limit=settings.max_total_upload_size,
        )
        document_id = await _finalize_document(
            courier_id,
            request,
            prepared[0],
            session_factory=session_factory,
        )
        async with session_factory() as session:
            return await _get_document(courier_id, document_id, session=session)
    finally:
        await _close_uploads([upload])


async def get_courier(courier_id: UUID, *, session: AsyncSession) -> Courier:
    """Вернуть полный aggregate, исключив документы в lifecycle deleting."""
    courier = await session.scalar(
        select(Courier)
        .where(Courier.id == courier_id)
        .options(*_aggregate_options())
        .execution_options(populate_existing=True)
    )
    if courier is None:
        raise NotFound("Courier not found", resource=Courier.__name__, pk=str(courier_id))
    return courier


async def list_couriers(
    page: PageParams,
    *,
    session: AsyncSession,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
) -> Page[Courier]:
    """Вернуть keyset-страницу полных aggregates с точными фильтрами."""
    where = []
    if email is not None:
        where.append(Courier.email == normalize_email(email))
    if phone is not None:
        where.append(Courier.phone == normalize_phone(phone))
    if full_name is not None:
        where.append(Courier.full_name == full_name)

    statement = (
        select(Courier)
        .where(*where)
        .options(*_aggregate_options())
        .order_by(Courier.created_at.desc(), Courier.id.desc())
        .limit(page.limit + 1)
    )
    if page.cursor is not None:
        position = decode_cursor(page.cursor)
        statement = statement.where(
            tuple_(Courier.created_at, Courier.id) < (position.created_at, position.id)
        )

    rows = list((await session.scalars(statement)).all())
    items = rows[: page.limit]
    next_cursor = None
    if len(rows) > page.limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return Page(items=items, next_cursor=next_cursor)


async def patch_courier(
    courier_id: UUID,
    patch: CourierPatch,
    *,
    session: AsyncSession,
) -> Courier:
    """Нормализовать natural keys, применить PATCH и consent transitions."""
    courier = await CRUD.get_or_404(Courier, courier_id, session)
    updates: dict[str, object] = {}
    if "email" in patch.model_fields_set:
        updates["email"] = normalize_email(cast(str, patch.email))
    if "phone" in patch.model_fields_set:
        updates["phone"] = normalize_phone(cast(str, patch.phone))
    normalized = patch.model_copy(update=updates)

    if "consent_to_processing" in normalized.model_fields_set:
        consent = cast(bool, normalized.consent_to_processing)
        if consent and not courier.consent_to_processing:
            courier.consent_at = datetime.now(tz=UTC)
        elif not consent:
            courier.consent_at = None
    try:
        await CRUD.update(courier, normalized, session)
    except IntegrityError as error:
        _raise_known_integrity(error)
    return await get_courier(courier_id, session=session)


async def delete_courier(courier_id: UUID, *, session: AsyncSession) -> None:
    """Пометить все Files deleting и удалить корень aggregate каскадно."""
    courier = await session.scalar(
        select(Courier).where(Courier.id == courier_id).with_for_update()
    )
    if courier is None:
        raise NotFound("Courier not found", resource=Courier.__name__, pk=str(courier_id))
    file_ids = list(
        (
            await session.scalars(
                select(CourierDocument.file_id).where(CourierDocument.courier_id == courier_id)
            )
        ).all()
    )
    for file_id in file_ids:
        await mark_file_deleting(session, file_id)
    await session.delete(courier)
    await session.flush()


async def create_platform_account(
    courier_id: UUID,
    request: PlatformAccountCreate,
    *,
    session: AsyncSession,
) -> CourierPlatformAccount:
    """Добавить курьеру новую уникальную delivery-платформу."""
    await _lock_courier(courier_id, session=session)
    account = CourierPlatformAccount(
        courier_id=courier_id,
        platform=request.platform,
        status=PlatformAccountStatus.PENDING,
    )
    session.add(account)
    try:
        await session.flush()
    except IntegrityError as error:
        _raise_known_integrity(error)
    return account


async def patch_platform_account(
    courier_id: UUID,
    account_id: UUID,
    patch: PlatformAccountPatch,
    *,
    session: AsyncSession,
) -> CourierPlatformAccount:
    """Сменить status вложенного account только внутри заданного Courier."""
    account = await _get_platform_account(courier_id, account_id, session=session)
    return await CRUD.update(account, patch, session)


async def patch_courier_document(
    courier_id: UUID,
    document_id: UUID,
    patch: CourierDocumentPatch,
    *,
    session: AsyncSession,
) -> CourierDocument:
    """Изменить metadata/hold видимого CourierDocument."""
    document = await _get_document(courier_id, document_id, session=session)
    return await CRUD.update(document, patch, session)


async def delete_courier_document(
    courier_id: UUID,
    document_id: UUID,
    *,
    session: AsyncSession,
) -> None:
    """Скрыть File через deleting и физически удалить Document metadata."""
    document = await _get_document(
        courier_id,
        document_id,
        session=session,
        for_update=True,
    )
    await mark_file_deleting(session, document.file_id)
    await session.delete(document)
    await session.flush()


async def purge_expired_documents(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: CourierModuleSettings,
    now: datetime | None = None,
) -> int:
    """Одним SKIP LOCKED batch удалить eligible Documents и пометить Files.

    Ошибка одного элемента откатывает только savepoint этого элемента. S3 не
    вызывается: физический lifecycle остаётся универсальной задачей storage.
    """
    current = now or datetime.now(tz=UTC)
    retention_days = {
        DocumentPurpose.PLATFORM_ONBOARDING: settings.retention_platform_onboarding_days,
        DocumentPurpose.EMPLOYMENT_COMPLIANCE: (settings.retention_employment_compliance_days),
        DocumentPurpose.OTHER: settings.retention_other_days,
    }
    eligible = and_(
        or_(
            *(
                and_(
                    CourierDocument.type == document_type,
                    CourierDocument.purpose == purpose,
                    CourierDocument.created_at <= current - timedelta(days=days),
                )
                for document_type in DocumentType
                for purpose, days in retention_days.items()
            )
        ),
        or_(
            CourierDocument.legal_hold_until.is_(None),
            CourierDocument.legal_hold_until <= current,
        ),
    )
    purged = 0
    async with session_factory() as session, session.begin():
        documents = list(
            (
                await session.scalars(
                    select(CourierDocument)
                    .where(eligible)
                    .order_by(CourierDocument.created_at, CourierDocument.id)
                    .limit(settings.retention_batch_size)
                    .with_for_update(skip_locked=True, of=CourierDocument)
                )
            ).all()
        )
        for document in documents:
            try:
                async with session.begin_nested():
                    await mark_file_deleting(session, document.file_id)
                    await session.delete(document)
                    await session.flush()
            except Exception as error:
                _logger.warning(
                    "courier.retention_document_failed",
                    document_id=str(document.id),
                    error=type(error).__name__,
                )
                continue
            purged += 1
    return purged


def _aggregate_options() -> tuple[ExecutableOption, ...]:
    """Явный eager contract aggregate без deleting File/Document."""
    documents = Courier.documents.and_(CourierDocument.file.has(File.status != FileStatus.DELETING))
    return (
        selectinload(Courier.platform_accounts),
        selectinload(documents).joinedload(CourierDocument.file),
    )


async def _find_by_identity(
    email: str,
    phone: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> Courier | None:
    """Найти natural-key match или поднять identity-split."""
    async with session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(Courier)
                    .where(or_(Courier.email == email, Courier.phone == phone))
                    .options(*_aggregate_options())
                    .order_by(Courier.id)
                )
            ).all()
        )
    if len(rows) > 1:
        raise Conflict(
            "Email and phone belong to different couriers",
            reason="identity-split",
        )
    return rows[0] if rows else None


async def _load_courier_by_identity(
    email: str,
    phone: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> Courier:
    """Перечитать committed aggregate по natural keys."""
    courier = await _find_by_identity(email, phone, session_factory=session_factory)
    if courier is None:
        raise RuntimeError("committed courier aggregate cannot be reloaded")
    return courier


def _validate_upload_count(
    documents: Sequence[CourierDocumentCreate],
    uploads: Sequence[DocumentUpload],
    *,
    settings: CourierModuleSettings,
) -> None:
    """Проверить cardinality документов до staging и S3."""
    if len(documents) > settings.max_documents:
        raise ValidationFailed(
            "Too many documents",
            reason="too-many-documents",
            limit=settings.max_documents,
        )
    if len(documents) != len(uploads):
        raise ValidationFailed(
            "Documents and files count must match",
            reason="document-file-count-mismatch",
        )


def _prepare_uploads(
    uploads: Sequence[DocumentUpload],
    *,
    bucket: str,
    uploader: MultipartUploader,
) -> list[_PreparedUpload]:
    """Проверить filename/MIME и назначить непрозрачные server keys."""
    prepared: list[_PreparedUpload] = []
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
            _PreparedUpload(
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


async def _create_staging_rows(
    uploads: Sequence[_PreparedUpload],
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


async def _upload_all(
    uploads: Sequence[_PreparedUpload],
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


async def _finalize_new_aggregate(
    request: CourierAggregateCreate,
    uploads: Sequence[_PreparedUpload],
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """Попытаться атомарно поглотить staging в новый aggregate."""
    courier_id = uuid7()
    values = request.model_dump(exclude={"platform_accounts", "documents"})
    values["id"] = courier_id
    values["consent_at"] = datetime.now(tz=UTC) if request.consent_to_processing else None
    staging_ids = [upload.id for upload in uploads]
    async with session_factory() as session, session.begin():
        inserted_id = await session.scalar(
            insert(Courier).values(**values).on_conflict_do_nothing().returning(Courier.id)
        )
        if inserted_id is None:
            if staging_ids:
                await session.execute(
                    update(FileUploadStaging)
                    .where(FileUploadStaging.id.in_(staging_ids))
                    .values(
                        status=StagingStatus.DELETING,
                        cleanup_claim_token=None,
                        cleanup_claimed_until=None,
                    )
                )
            return False

        staged = await consume_uploaded_staging(session, staging_ids)
        staged_by_id = {row.id: row for row in staged}
        for account in request.platform_accounts:
            session.add(
                CourierPlatformAccount(
                    courier_id=courier_id,
                    platform=account.platform,
                    status=PlatformAccountStatus.PENDING,
                )
            )
        for document, prepared in zip(request.documents, uploads, strict=True):
            row = staged_by_id[prepared.id]
            file = await _create_ready_file(row, session=session)
            session.add(
                CourierDocument(
                    courier_id=courier_id,
                    file_id=file.id,
                    type=document.type,
                    purpose=document.purpose,
                    legal_hold_until=document.legal_hold_until,
                )
            )
        await session.flush()
    return True


async def _finalize_document(
    courier_id: UUID,
    request: CourierDocumentCreate,
    upload: _PreparedUpload,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    """Поглотить один staging в ready File и Document под lock Courier."""
    document_id = uuid7()
    async with session_factory() as session, session.begin():
        await _lock_courier(courier_id, session=session)
        staged = await consume_uploaded_staging(session, [upload.id])
        file = await _create_ready_file(staged[0], session=session)
        session.add(
            CourierDocument(
                id=document_id,
                courier_id=courier_id,
                file_id=file.id,
                type=request.type,
                purpose=request.purpose,
                legal_hold_until=request.legal_hold_until,
            )
        )
        await session.flush()
    return document_id


async def _create_ready_file(
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


async def _get_document(
    courier_id: UUID,
    document_id: UUID,
    *,
    session: AsyncSession,
    for_update: bool = False,
) -> CourierDocument:
    """Найти видимый Document по собственному id и courier_id."""
    statement = (
        select(CourierDocument)
        .join(CourierDocument.file)
        .where(
            CourierDocument.id == document_id,
            CourierDocument.courier_id == courier_id,
            File.status != FileStatus.DELETING,
        )
        .options(joinedload(CourierDocument.file))
    )
    if for_update:
        statement = statement.with_for_update(of=CourierDocument)
    document = await session.scalar(statement)
    if document is None:
        raise NotFound(
            "CourierDocument not found",
            resource=CourierDocument.__name__,
            pk=str(document_id),
        )
    return document


async def _get_platform_account(
    courier_id: UUID,
    account_id: UUID,
    *,
    session: AsyncSession,
) -> CourierPlatformAccount:
    """Найти account только внутри указанного Courier."""
    account = await session.scalar(
        select(CourierPlatformAccount).where(
            CourierPlatformAccount.id == account_id,
            CourierPlatformAccount.courier_id == courier_id,
        )
    )
    if account is None:
        raise NotFound(
            "CourierPlatformAccount not found",
            resource=CourierPlatformAccount.__name__,
            pk=str(account_id),
        )
    return account


async def _require_courier(courier_id: UUID, *, session: AsyncSession) -> Courier:
    """Вернуть Courier или единообразный 404."""
    courier = await session.get(Courier, courier_id)
    if courier is None:
        raise NotFound("Courier not found", resource=Courier.__name__, pk=str(courier_id))
    return courier


async def _lock_courier(courier_id: UUID, *, session: AsyncSession) -> None:
    """Сериализовать дочерний write с каскадным DELETE Courier."""
    found = await session.scalar(
        select(Courier.id).where(Courier.id == courier_id).with_for_update()
    )
    if found is None:
        raise NotFound("Courier not found", resource=Courier.__name__, pk=str(courier_id))


def _raise_known_integrity(error: IntegrityError) -> NoReturn:
    """Преобразовать только известные unique constraints в Conflict."""
    constraint = _constraint_name(error)
    if constraint == "uq_couriers_email":
        raise Conflict("Email already belongs to another courier", field="email") from error
    if constraint == "uq_couriers_phone":
        raise Conflict("Phone already belongs to another courier", field="phone") from error
    if constraint == "uq_courier_platform_accounts_courier_id_platform":
        raise Conflict("Courier already has this platform", reason="duplicate-platform") from error
    raise error


def _constraint_name(error: IntegrityError) -> str | None:
    """Достать имя Postgres constraint из asyncpg adapter chain."""
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


async def _close_uploads(uploads: Sequence[DocumentUpload]) -> None:
    """Закрыть все UploadFile на каждой ветке, не раскрывая их имена в лог."""
    for upload in uploads:
        try:
            await upload.close()
        except Exception as error:
            _logger.warning(
                "courier.upload_close_failed",
                error=type(error).__name__,
            )
