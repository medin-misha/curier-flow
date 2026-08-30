"""Манифест documents и lifespan его S3-клиента."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.kernel.registry import Module
from app.modules.documents.handlers import router
from app.modules.documents.services import DocumentsRuntime, DocumentsSettings, documents_settings
from app.platform.s3 import S3Settings, s3_settings, storage


def documents_lifespan(
    *,
    storage_config: S3Settings,
    settings: DocumentsSettings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Создать долгоживущий S3-клиент генератора документов."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with storage(storage_config) as objects:
            app.state.documents_runtime = DocumentsRuntime(objects=objects, settings=settings)
            yield

    return lifespan


documents_module: Final = Module(
    name="documents",
    prefix="/document-templates",
    router=router,
    settings=DocumentsSettings,
    models="app.modules.documents.models",
    lifespan=documents_lifespan(storage_config=s3_settings, settings=documents_settings),
)
