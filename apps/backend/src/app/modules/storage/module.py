"""Манифест модуля storage и жизненный цикл его клиента хранилища."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.kernel.registry import Module
from app.modules.storage.handlers import router
from app.modules.storage.services import FileStorage, StorageSettings, storage_settings
from app.modules.storage.tasks import (
    cleanup_file_upload_staging,
    delete_marked_files,
    sweep_orphaned_uploads,
)
from app.platform.s3 import S3Settings, s3_settings, storage


def storage_lifespan(
    *,
    storage_config: S3Settings,
    limits: StorageSettings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Собрать lifespan модуля: клиент хранилища на всё время жизни процесса.

    Принимает настройки хранилища и лимиты модуля, возвращает контекстный
    менеджер для манифеста.

    Фабрика, а не готовый lifespan: настройки передаются аргументами, поэтому
    тесты подставляют адрес своего контейнера, не трогая глобальные настройки
    процесса.

    Клиент создаётся один раз: он держит пул HTTP-соединений и разбирает
    описание сервиса в несколько мегабайт, а подписать ссылку нужно на каждый
    запрос. Сети создание не касается, поэтому лежащее хранилище старт
    приложения не задерживает.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with storage(storage_config) as objects:
            app.state.file_storage = FileStorage(objects=objects, limits=limits)
            yield

    return lifespan


storage_module: Final = Module(
    name="storage",
    router=router,
    # Модуль называется по своей роли, а ресурс — по тому, чем управляет:
    # ручки живут на `/files`, а не на `/storage`.
    prefix="/files",
    settings=StorageSettings,
    models="app.modules.storage.models",
    tasks=(sweep_orphaned_uploads, delete_marked_files, cleanup_file_upload_staging),
    lifespan=storage_lifespan(storage_config=s3_settings, limits=storage_settings),
)
