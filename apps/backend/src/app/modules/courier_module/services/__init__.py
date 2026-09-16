"""Публичный фасад бизнес-сервисов courier_module."""

from app.modules.courier_module.services.common import normalize_email, normalize_phone
from app.modules.courier_module.services.couriers import (
    AggregateCreateResult,
    bulk_delete_couriers,
    create_courier_aggregate,
    delete_courier,
    get_courier,
    list_couriers,
    patch_courier,
)
from app.modules.courier_module.services.documents import (
    create_courier_document,
    delete_courier_document,
    patch_courier_document,
)
from app.modules.courier_module.services.platform_accounts import (
    bulk_patch_platform_status,
    create_platform_account,
    patch_platform_account,
)
from app.modules.courier_module.services.retention import purge_expired_documents
from app.modules.courier_module.services.settings import (
    CourierModuleSettings,
    courier_module_settings,
)
from app.modules.courier_module.services.uploads import DocumentUpload

__all__ = (
    "AggregateCreateResult",
    "CourierModuleSettings",
    "DocumentUpload",
    "bulk_delete_couriers",
    "bulk_patch_platform_status",
    "courier_module_settings",
    "create_courier_aggregate",
    "create_courier_document",
    "create_platform_account",
    "delete_courier",
    "delete_courier_document",
    "get_courier",
    "list_couriers",
    "normalize_email",
    "normalize_phone",
    "patch_courier",
    "patch_courier_document",
    "patch_platform_account",
    "purge_expired_documents",
)
