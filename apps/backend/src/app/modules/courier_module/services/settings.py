"""Настройки courier_module."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CourierModuleSettings(BaseSettings):
    """Upload limits, retention policy и расписание courier_module."""

    model_config = SettingsConfigDict(
        env_prefix="courier_module_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_documents: int = Field(default=20, ge=0)
    max_total_upload_size: int = Field(default=104_857_600, gt=0)
    retention_platform_onboarding_days: int = Field(default=90, ge=1)
    retention_employment_compliance_days: int = Field(default=1825, ge=1)
    retention_other_days: int = Field(default=365, ge=1)
    retention_cron: str = "29 2 * * *"
    retention_batch_size: int = Field(default=100, ge=1)


courier_module_settings = CourierModuleSettings()
