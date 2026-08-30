"""Манифест модуля finance."""

from typing import Final

from app.kernel.registry import Module
from app.modules.finance.handlers import router

finance_module: Final = Module(
    name="finance",
    router=router,
    prefix="/receipts",
    models="app.modules.finance.models",
)
