"""Публичный фасад бизнес-логики административного модуля."""

from app.modules.admin.services.accounts import (
    activate_admin,
    authenticate_current_admin,
    create_admin,
    deactivate_admin,
    get_admin,
    list_admins,
    patch_admin,
    reset_admin_password,
)
from app.modules.admin.services.authentication import (
    TokenGrant,
    login_admin,
    logout_admin,
    purge_expired_refresh_tokens,
    refresh_admin_tokens,
)
from app.modules.admin.services.bootstrap import bootstrap_first_admin
from app.modules.admin.services.notifications import fan_out_courier_registration_notifications
from app.modules.admin.services.settings import AdminSettings, admin_settings

__all__ = [
    "AdminSettings",
    "TokenGrant",
    "activate_admin",
    "admin_settings",
    "authenticate_current_admin",
    "bootstrap_first_admin",
    "create_admin",
    "deactivate_admin",
    "fan_out_courier_registration_notifications",
    "get_admin",
    "list_admins",
    "login_admin",
    "logout_admin",
    "patch_admin",
    "purge_expired_refresh_tokens",
    "refresh_admin_tokens",
    "reset_admin_password",
]
