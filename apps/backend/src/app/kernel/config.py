"""Общие настройки приложения.

Здесь живёт только то, что нужно всему сервису сразу: идентификация сборки,
логирование и подключение к БД. Настройки конкретной подсистемы (брокер, S3,
JWT) объявляются рядом со своим владельцем — иначе этот модуль превращается
в глобальную свалку, а изменение настройки одного модуля перекомпилирует
контекст всех остальных.

Значения читаются из окружения и из файла `.env`, если он есть. Дефолты
совпадают с `.env.example`, поэтому шаблон запускается сразу после clone.
"""

from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Окружение влияет на формат логов, показ трейсбеков и содержимое /health/info.
Environment = Literal["local", "dev", "staging", "prod"]
LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Настройки процесса, собранные из окружения.

    Экземпляр создаётся один раз на импорт модуля (`settings` ниже): настройки
    неизменны в течение жизни процесса, а чтение окружения по требованию
    прятало бы зависимость от него внутрь бизнес-кода.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Один .env документирует настройки всех подсистем, поэтому в нём есть
        # переменные других Settings-классов. Запрет лишних полей ронял бы
        # старт на ровном месте.
        extra="ignore",
    )

    app_env: Environment = "local"
    app_name: str = "backend-template"
    app_version: str = "0.1.0"
    debug: bool = True

    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    #: Базовый URI типов ошибок в ответах problem+json: `type` собирается как
    #: `{errors_base_url}/{code}`. Настройка, а не константа, потому что в
    #: RFC 9457 `type` — это ссылка на описание проблемы, и у сервиса с
    #: публичной документацией она указывает на реальную страницу.
    errors_base_url: str = "https://errors.local"

    database_dsn: PostgresDsn = PostgresDsn("postgresql+asyncpg://app:app@localhost:5432/app")
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=5, ge=0)
    database_echo: bool = False


#: Единственный экземпляр настроек процесса.
settings = Settings()
