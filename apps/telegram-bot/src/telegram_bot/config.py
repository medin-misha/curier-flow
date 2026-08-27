"""Конфигурация процесса из переменных окружения."""

from typing import Literal

from pydantic import AmqpDsn, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки sending-only worker без рабочих секретов по умолчанию."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "telegram-bot"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"
    rabbitmq_dsn: AmqpDsn = AmqpDsn("amqp://guest:guest@localhost:5672/")
    telegram_bot_token: SecretStr = Field(min_length=1)
    telegram_max_retries: int = Field(default=5, ge=0)
    telegram_api_timeout: float = Field(default=10, gt=0)
    telegram_shutdown_timeout: float = Field(default=30, gt=0)
