"""ORM-модели административного модуля."""

from app.modules.admin.models.admin import Admin
from app.modules.admin.models.refresh_token import AdminRefreshToken

__all__ = ["Admin", "AdminRefreshToken"]
