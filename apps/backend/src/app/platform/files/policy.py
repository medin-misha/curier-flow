"""Единая политика типов и размера файлов и настройки staging cleanup."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class FilePolicySettings(BaseSettings):
    """Совместимые STORAGE_* настройки общей политики одного файла."""

    model_config = SettingsConfigDict(
        env_prefix="storage_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_file_size: int = Field(default=26_214_400, gt=0)
    allowed_content_types: Annotated[frozenset[str], NoDecode] = frozenset(
        {"image/png", "image/jpeg", "image/webp", "application/pdf"}
    )

    @field_validator("allowed_content_types", mode="before")
    @classmethod
    def _split_types(cls, value: object) -> object:
        """Разобрать CSV allow-list и нормализовать MIME types."""
        if isinstance(value, str):
            return {item.strip().lower() for item in value.split(",") if item.strip()}
        return value


class FileUploadStagingSettings(BaseSettings):
    """TTL, lease и расписание durable staging cleanup."""

    model_config = SettingsConfigDict(
        env_prefix="file_upload_staging_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ttl: int = Field(default=86_400, gt=0)
    cleanup_cron: str = "*/15 * * * *"
    batch_size: int = Field(default=100, ge=1)
    claim_ttl: int = Field(default=300, gt=0)


@dataclass(frozen=True, slots=True)
class FilePolicy:
    """Неизменяемая политика проверки MIME type и размера одного файла."""

    max_file_size: int
    allowed_content_types: frozenset[str]

    @classmethod
    def from_settings(cls, settings: FilePolicySettings) -> "FilePolicy":
        """Собрать политику из pydantic-settings без повторного чтения env."""
        return cls(
            max_file_size=settings.max_file_size,
            allowed_content_types=settings.allowed_content_types,
        )

    def normalize_content_type(self, content_type: str) -> str:
        """Нормализовать заявленный MIME type без sniffing содержимого."""
        return content_type.strip().lower()

    def allows_content_type(self, content_type: str) -> bool:
        """Проверить нормализованный MIME type по единому allow-list."""
        return self.normalize_content_type(content_type) in self.allowed_content_types


file_policy_settings = FilePolicySettings()
file_policy = FilePolicy.from_settings(file_policy_settings)
staging_settings = FileUploadStagingSettings()
