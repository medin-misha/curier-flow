"""Защищённый HTTP-контракт DOCX-шаблонов."""

import re
from http import HTTPStatus
from typing import Annotated, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.kernel.db import session as db_session
from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.pagination import Page, PageParams
from app.kernel.security.authentication import authenticated
from app.modules.documents.schemas.requests import DocumentRenderRequest, DocumentTemplateCreate
from app.modules.documents.schemas.responses import DocumentTemplateResponse
from app.modules.documents.services import (
    DOCX_CONTENT_TYPE,
    DocumentsRuntime,
    create_template,
    delete_template,
    get_template,
    list_templates,
    render_document,
)

_UNSAFE_FILENAME = re.compile(r"[/\\\x00-\x1f\x7f]")


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Отдать фабрику для операций с явной границей вокруг S3."""
    return db_session.session_factory


async def get_documents_runtime(request: Request) -> DocumentsRuntime:
    """Достать S3-клиент и лимиты из lifespan модуля."""
    return cast(DocumentsRuntime, request.app.state.documents_runtime)


Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
Runtime = Annotated[DocumentsRuntime, Depends(get_documents_runtime)]
PageQuery = Annotated[PageParams, Depends()]

router = APIRouter(tags=["document-templates"])


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Create a DOCX document template",
    responses={HTTPStatus.OK: {"model": DocumentTemplateResponse, "description": "Exact retry"}},
)
@authenticated
async def create(
    body: DocumentTemplateCreate,
    response: Response,
    sessions: Sessions,
    runtime: Runtime,
) -> DocumentTemplateResponse:
    """Проверить ready File и сохранить найденные placeholders."""
    result = await create_template(body, session_factory=sessions, runtime=runtime)
    response.status_code = HTTPStatus.CREATED if result.created else HTTPStatus.OK
    return DocumentTemplateResponse.model_validate(result.template)


@router.get("", summary="List document templates")
@authenticated
async def list_page(page: PageQuery, session: RoSession) -> Page[DocumentTemplateResponse]:
    """Отдать keyset-страницу шаблонов."""
    found = await list_templates(page, session=session)
    return Page[DocumentTemplateResponse](
        items=[DocumentTemplateResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/{template_id}", summary="Document template by id")
@authenticated
async def retrieve(template_id: UUID, session: RoSession) -> DocumentTemplateResponse:
    """Отдать один шаблон и его схему полей."""
    return DocumentTemplateResponse.model_validate(await get_template(template_id, session=session))


@router.post("/{template_id}/render", summary="Render a transient DOCX document")
@authenticated
async def render(
    template_id: UUID,
    body: DocumentRenderRequest,
    sessions: Sessions,
    runtime: Runtime,
) -> Response:
    """Вернуть заполненный DOCX без записи результата в File-каталог."""
    rendered = await render_document(
        template_id,
        body,
        session_factory=sessions,
        runtime=runtime,
    )
    return Response(
        content=rendered.body,
        media_type=DOCX_CONTENT_TYPE,
        headers={
            "Content-Disposition": _content_disposition(rendered.name, template_id),
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/{template_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a document template",
)
@authenticated
async def remove(template_id: UUID, uow: Uow) -> None:
    """Удалить шаблон, не удаляя его исходный File."""
    await delete_template(template_id, session=uow)


def _content_disposition(name: str, template_id: UUID) -> str:
    """Собрать безопасное ASCII fallback и UTF-8 имя вложения."""
    clean = _UNSAFE_FILENAME.sub("_", name).strip(" .")[:150] or "document"
    if not clean.lower().endswith(".docx"):
        clean = f"{clean}.docx"
    encoded = quote(clean, safe="")
    return f"attachment; filename=\"document-{template_id}.docx\"; filename*=UTF-8''{encoded}"
