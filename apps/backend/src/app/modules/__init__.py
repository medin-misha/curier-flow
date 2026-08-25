"""Реестр бизнес-модулей приложения.

`MODULES` — единственное место, где перечислен состав сервиса: из него
собираются роутер, lifespan, метаданные Alembic, подписчики, задачи и
топология брокера. Новый модуль подключается одной строкой здесь; пока его
манифеста нет в списке, его нет и в приложении. Полноту списка сторожит
`tests/test_registry.py`.
"""

from typing import Final

from app.kernel.registry import Module
from app.modules.admin.module import admin_module
from app.modules.courier_module.module import courier_module
from app.modules.health.module import health_module
from app.modules.storage.module import storage_module

MODULES: Final[tuple[Module, ...]] = (
    health_module,
    storage_module,
    courier_module,
    admin_module,
)
