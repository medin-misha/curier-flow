"""Публичный фасад бизнес-сервисов transport_module."""

from app.modules.transport_module.services.components import (
    create_component,
    delete_component,
    list_components,
    patch_component,
)
from app.modules.transport_module.services.queries import get_component, get_rental, get_transport
from app.modules.transport_module.services.rentals import (
    attach_contract,
    close_rental,
    create_rental,
    list_rentals,
)
from app.modules.transport_module.services.transports import (
    create_transport,
    delete_transport,
    list_transports,
    patch_transport,
)

__all__ = [
    "attach_contract",
    "close_rental",
    "create_component",
    "create_rental",
    "create_transport",
    "delete_component",
    "delete_transport",
    "get_component",
    "get_rental",
    "get_transport",
    "list_components",
    "list_rentals",
    "list_transports",
    "patch_component",
    "patch_transport",
]
