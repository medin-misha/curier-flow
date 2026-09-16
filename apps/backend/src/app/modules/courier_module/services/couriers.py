"""Создание, чтение, изменение и удаление Courier aggregate."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils.compat import uuid7

from app.kernel.db.crud import CRUD
from app.kernel.errors import Conflict, NotFound, ValidationFailed
from app.kernel.events.bus import emit
from app.kernel.pagination import Page, PageParams, decode_cursor, encode_cursor
from app.modules.courier_module.events import CourierRegistered
from app.modules.courier_module.models import (
    Courier,
    CourierDocument,
    CourierPlatformAccount,
    PlatformAccountStatus,
)
from app.modules.courier_module.schemas.requests import (
    CourierAggregateCreate,
    CourierDocumentCreate,
    CourierPatch,
)
from app.modules.courier_module.services.common import (
    normalize_email,
    normalize_phone,
    raise_known_integrity,
)
from app.modules.courier_module.services.queries import (
    aggregate_options,
    find_by_identity,
    load_courier_by_identity,
    lock_couriers,
)
from app.modules.courier_module.services.settings import CourierModuleSettings
from app.modules.courier_module.services.uploads import (
    DocumentUpload,
    PreparedUpload,
    close_uploads,
    create_ready_file,
    create_staging_rows,
    prepare_uploads,
    upload_all,
)
from app.platform.files import (
    FileUploadStaging,
    MultipartUploader,
    StagingStatus,
    consume_uploaded_staging,
    mark_file_deleting,
)


@dataclass(frozen=True, slots=True)
class AggregateCreateResult:
    """Courier aggregate и признак фактического создания."""

    courier: Courier
    created: bool


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
        existing = await find_by_identity(
            normalized.email,
            normalized.phone,
            session_factory=session_factory,
        )
        if existing is not None:
            return AggregateCreateResult(courier=existing, created=False)

        prepared = prepare_uploads(
            uploads,
            bucket=uploader.objects.bucket,
            uploader=uploader,
        )
        await create_staging_rows(prepared, session_factory=session_factory)
        await upload_all(
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
            courier = await load_courier_by_identity(
                normalized.email,
                normalized.phone,
                session_factory=session_factory,
            )
            return AggregateCreateResult(courier=courier, created=True)

        winner = await find_by_identity(
            normalized.email,
            normalized.phone,
            session_factory=session_factory,
        )
        if winner is None:
            raise Conflict("Courier identity changed concurrently", reason="identity-conflict")
        return AggregateCreateResult(courier=winner, created=False)
    finally:
        await close_uploads(uploads)


async def get_courier(courier_id: UUID, *, session: AsyncSession) -> Courier:
    """Вернуть полный aggregate, исключив документы в lifecycle deleting."""
    courier = await session.scalar(
        select(Courier)
        .where(Courier.id == courier_id)
        .options(*aggregate_options())
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
    status: PlatformAccountStatus | None = None,
) -> Page[Courier]:
    """Вернуть keyset-страницу aggregates с точными scalar/status-фильтрами."""
    where = []
    if email is not None:
        where.append(Courier.email == normalize_email(email))
    if phone is not None:
        where.append(Courier.phone == normalize_phone(phone))
    if full_name is not None:
        where.append(Courier.full_name == full_name)
    if status is not None:
        where.append(Courier.platform_accounts.any(CourierPlatformAccount.status == status))

    statement = (
        select(Courier)
        .where(*where)
        .options(*aggregate_options())
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
        raise_known_integrity(error)
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
    try:
        for file_id in file_ids:
            await mark_file_deleting(session, file_id)
        await session.delete(courier)
        await session.flush()
    except IntegrityError as error:
        raise_known_integrity(error)


async def bulk_delete_couriers(courier_ids: Sequence[UUID], *, session: AsyncSession) -> int:
    """Удалить всю пачку с прежним файловым lifecycle и защитой договоров."""
    locked_ids = await lock_couriers(courier_ids, session=session)
    for courier_id in locked_ids:
        try:
            await delete_courier(courier_id, session=session)
        except Conflict as error:
            error.extra["courier_id"] = str(courier_id)
            raise
    return len(locked_ids)


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


async def _finalize_new_aggregate(
    request: CourierAggregateCreate,
    uploads: Sequence[PreparedUpload],
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

        emit(
            session,
            CourierRegistered(
                courier_id=inserted_id,
                full_name=request.full_name,
                contact_platform=request.contact_platform,
                contact=request.contact,
                platforms=[account.platform for account in request.platform_accounts],
            ),
        )
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
            file = await create_ready_file(row, session=session)
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
