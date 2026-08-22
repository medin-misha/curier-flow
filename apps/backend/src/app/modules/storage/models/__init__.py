"""Модели модуля storage.

Пакет, а не один файл: alembic импортирует его по имени из манифеста
(`Module.models`), и таблицы обязаны попасть в метаданные от этого импорта.
"""

from app.modules.storage.models.file import File, FileStatus, FileUploadStaging, StagingStatus

__all__ = ["File", "FileStatus", "FileUploadStaging", "StagingStatus"]
