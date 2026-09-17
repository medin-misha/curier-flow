"""Манифест transport_module."""

from typing import Final

from app.kernel.registry import Module
from app.modules.transport_module.handlers import router
from app.modules.transport_module.subscribers import sync_courier_profile

transport_module: Final = Module(
    name="transport_module",
    router=router,
    prefix="/transport",
    models="app.modules.transport_module.models",
    subscribers=(sync_courier_profile,),
)
