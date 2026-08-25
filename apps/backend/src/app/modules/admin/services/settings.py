"""Настройки bootstrap, refresh cookie и retention административного модуля."""

from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.kernel.config import settings


class AdminSettings(BaseSettings):
    """Настройки административной аутентификации."""

    model_config = SettingsConfigDict(
        env_prefix="admin_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    bootstrap_username: str = ""
    bootstrap_password: SecretStr = SecretStr("")
    bootstrap_telegram_id: int | None = None

    refresh_cookie_name: str = "admin_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "strict"
    refresh_cleanup_cron: str = "17 4 * * *"

    @model_validator(mode="after")
    def _validate_cookie_policy(self) -> Self:
        """Не разрешить передавать production refresh cookie без TLS."""
        if settings.app_env == "prod" and not self.refresh_cookie_secure:
            raise ValueError("ADMIN_REFRESH_COOKIE_SECURE must be true in production")
        if self.refresh_cookie_samesite == "none" and not self.refresh_cookie_secure:
            raise ValueError("SameSite=None refresh cookie requires Secure=true")
        return self


admin_settings = AdminSettings()
