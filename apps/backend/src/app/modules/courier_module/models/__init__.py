"""ORM-модели aggregate courier_module, импортируемые Alembic как пакет."""

from app.modules.courier_module.models.courier import Courier
from app.modules.courier_module.models.document import (
    CourierDocument,
    DocumentPurpose,
    DocumentType,
)
from app.modules.courier_module.models.platform_account import (
    CourierPlatformAccount,
    DeliveryPlatform,
    PlatformAccountStatus,
)

__all__ = [
    "Courier",
    "CourierDocument",
    "CourierPlatformAccount",
    "DeliveryPlatform",
    "DocumentPurpose",
    "DocumentType",
    "PlatformAccountStatus",
]
