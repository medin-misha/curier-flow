"""Манифест courier_module и lifespan streaming uploader."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.kernel.registry import Module
from app.modules.courier_module.handlers import router
from app.modules.courier_module.services import CourierModuleSettings
from app.modules.courier_module.tasks import purge_expired_documents
from app.platform.files import FilePolicy, MultipartUploader, file_policy
from app.platform.s3 import S3Settings, s3_settings, storage


def courier_lifespan(
    *,
    storage_config: S3Settings,
    policy: FilePolicy,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Создать и закрыть долгоживущий platform uploader процесса uvicorn."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with storage(storage_config) as objects:
            app.state.courier_uploader = MultipartUploader(objects=objects, policy=policy)
            yield

    return lifespan


courier_module: Final = Module(
    name="courier_module",
    prefix="/courier",
    router=router,
    settings=CourierModuleSettings,
    models="app.modules.courier_module.models",
    tasks=(purge_expired_documents,),
    lifespan=courier_lifespan(storage_config=s3_settings, policy=file_policy),
)
