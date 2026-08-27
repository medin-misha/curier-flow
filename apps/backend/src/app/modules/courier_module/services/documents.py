"""Создание, изменение и удаление документов Courier."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils.compat import uuid7

from app.kernel.db.crud import CRUD
from app.modules.courier_module.models import CourierDocument
from app.modules.courier_module.schemas.requests import (
    CourierDocumentCreate,
    CourierDocumentPatch,
)
from app.modules.courier_module.services.queries import (
    get_document,
    lock_courier,
    require_courier,
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
from app.platform.files import MultipartUploader, consume_uploaded_staging, mark_file_deleting


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
            await require_courier(courier_id, session=session)

        prepared = prepare_uploads(
            [upload],
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
        document_id = await _finalize_document(
            courier_id,
            request,
            prepared[0],
            session_factory=session_factory,
        )
        async with session_factory() as session:
            return await get_document(courier_id, document_id, session=session)
    finally:
        await close_uploads([upload])


async def patch_courier_document(
    courier_id: UUID,
    document_id: UUID,
    patch: CourierDocumentPatch,
    *,
    session: AsyncSession,
) -> CourierDocument:
    """Изменить metadata/hold видимого CourierDocument."""
    document = await get_document(courier_id, document_id, session=session)
    return await CRUD.update(document, patch, session)


async def delete_courier_document(
    courier_id: UUID,
    document_id: UUID,
    *,
    session: AsyncSession,
) -> None:
    """Скрыть File через deleting и физически удалить Document metadata."""
    document = await get_document(
        courier_id,
        document_id,
        session=session,
        for_update=True,
    )
    await mark_file_deleting(session, document.file_id)
    await session.delete(document)
    await session.flush()


async def _finalize_document(
    courier_id: UUID,
    request: CourierDocumentCreate,
    upload: PreparedUpload,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    """Поглотить один staging в ready File и Document под lock Courier."""
    document_id = uuid7()
    async with session_factory() as session, session.begin():
        await lock_courier(courier_id, session=session)
        staged = await consume_uploaded_staging(session, [upload.id])
        file = await create_ready_file(staged[0], session=session)
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
