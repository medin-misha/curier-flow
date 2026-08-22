"""Compatibility re-export ORM-моделей общего platform file catalog."""

from app.platform.files.models import File, FileStatus, FileUploadStaging, StagingStatus

__all__ = ["File", "FileStatus", "FileUploadStaging", "StagingStatus"]
