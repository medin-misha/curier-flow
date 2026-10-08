"""Настройки: дефолты, чтение .env, работа без него."""

from pathlib import Path

from app.kernel.config import Settings, settings

#: Значения из .env.example. Расхождение означает, что шаблон после clone
#: поднимется не на той конфигурации, которую обещает документация.
EXPECTED_DEFAULTS = {
    "app_env": "local",
    "app_name": "backend-template",
    "app_version": "0.1.0",
    "debug": True,
    "log_level": "INFO",
    "log_format": "console",
    "errors_base_url": "https://errors.local",
    "database_pool_size": 10,
    "database_max_overflow": 5,
    "database_echo": False,
}


def test_defaults_match_env_example() -> None:
    actual = {name: Settings.model_fields[name].default for name in EXPECTED_DEFAULTS}

    assert actual == EXPECTED_DEFAULTS


def test_default_dsn_uses_asyncpg() -> None:
    """Синхронный драйвер в DSN уронил бы приложение только в рантайме."""
    assert str(Settings.model_fields["database_dsn"].default).startswith("postgresql+asyncpg://")


def test_env_file_is_read_from_dot_env() -> None:
    assert Settings.model_config["env_file"] == ".env"


def test_settings_build_without_env_file() -> None:
    """Отсутствие .env — норма: в проде конфигурация приходит окружением."""
    assert Settings(_env_file=None).app_name


def test_env_file_overrides_defaults(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=from-env-file\nDATABASE_POOL_SIZE=42\n", encoding="utf-8")

    loaded = Settings(_env_file=env_file)

    assert loaded.app_name == "from-env-file"
    assert loaded.database_pool_size == 42


def test_module_singleton_is_ready_to_use() -> None:
    assert settings.app_name
    assert str(settings.database_dsn)


def test_unknown_env_vars_are_ignored() -> None:
    """В .env лежат настройки других подсистем; падать на них нельзя."""
    assert Settings.model_config["extra"] == "ignore"
