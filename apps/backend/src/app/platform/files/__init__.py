"""Публичный контракт общего file catalog, staging, policy и uploader."""

from app.platform.files.catalog import (
    StagingCleanupClaim,
    StagingNotUploadedError,
    claim_stale_staging,
    consume_uploaded_staging,
    create_file,
    create_staging,
    delete_claimed_staging,
    get_file,
    mark_file_deleting,
    mark_file_ready,
    mark_staging_uploaded,
    record_cleanup_error,
    record_multipart_upload_id,
)
from app.platform.files.events import FileConfirmed
from app.platform.files.models import File, FileStatus, FileUploadStaging, StagingStatus
from app.platform.files.policy import (
    FilePolicy,
    FilePolicySettings,
    FileUploadStagingSettings,
    file_policy,
    file_policy_settings,
    staging_settings,
)
from app.platform.files.uploader import (
    AsyncReadable,
    MultipartUploader,
    UploadRejectedError,
    UploadResult,
)

__all__ = [
    "AsyncReadable",
    "File",
    "FileConfirmed",
    "FilePolicy",
    "FilePolicySettings",
    "FileStatus",
    "FileUploadStaging",
    "FileUploadStagingSettings",
    "MultipartUploader",
    "StagingCleanupClaim",
    "StagingNotUploadedError",
    "StagingStatus",
    "UploadRejectedError",
    "UploadResult",
    "claim_stale_staging",
    "consume_uploaded_staging",
    "create_file",
    "create_staging",
    "delete_claimed_staging",
    "file_policy",
    "file_policy_settings",
    "get_file",
    "mark_file_deleting",
    "mark_file_ready",
    "mark_staging_uploaded",
    "record_cleanup_error",
    "record_multipart_upload_id",
    "staging_settings",
]
