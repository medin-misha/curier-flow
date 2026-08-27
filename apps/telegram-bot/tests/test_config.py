"""Тесты настроек и защиты bot token."""

import logging
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from telegram_bot.config import Settings
from telegram_bot.logging import configure_logging


def test_token_is_required_and_non_empty() -> None:
    """У рабочего token нет default и пустого допустимого значения."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_bot_token="")


def test_defaults_match_env_example() -> None:
    """Документированные defaults совпадают с кодом."""
    settings = Settings(_env_file=None, telegram_bot_token="stub-token")

    assert settings.app_env == "local"
    assert settings.app_name == "telegram-bot"
    assert settings.log_level == "INFO"
    assert settings.log_format == "console"
    assert str(settings.rabbitmq_dsn) == "amqp://guest:guest@localhost:5672/"
    assert settings.telegram_max_retries == 5
    assert settings.telegram_api_timeout == 10
    assert settings.telegram_shutdown_timeout == 30

    example = Path(".env.example").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=\n" in example
    assert "TELEGRAM_MAX_RETRIES=5\n" in example


def test_token_is_secret_in_settings_repr() -> None:
    """SecretStr маскирует token в repr и model dump."""
    raw_token = "stub-super-secret-token"
    settings = Settings(_env_file=None, telegram_bot_token=raw_token)

    assert isinstance(settings.telegram_bot_token, SecretStr)
    assert raw_token not in repr(settings)
    assert raw_token not in repr(settings.model_dump())
    assert settings.telegram_bot_token.get_secret_value() == raw_token


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telegram_max_retries", -1),
        ("telegram_api_timeout", 0),
        ("telegram_shutdown_timeout", 0),
    ],
)
def test_numeric_limits_are_validated(field: str, value: int) -> None:
    """Отрицательные limits и нулевые timeout запрещены."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_bot_token="stub-token", **{field: value})


def test_dependency_loggers_remain_warning_at_app_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token-bearing URL и AMQP body не проходят dependency DEBUG/INFO logs."""
    configured_levels: dict[str, int] = {}

    class LoggerSpy:
        """Минимальный logger, записывающий установленный level."""

        def __init__(self, name: str) -> None:
            self.name = name

        def setLevel(self, level: int) -> None:  # noqa: N802
            """Записать level стандартного logger API."""
            configured_levels[self.name] = level

    with monkeypatch.context() as isolated:
        isolated.setattr(logging, "basicConfig", lambda **_kwargs: None)
        isolated.setattr(logging, "getLogger", LoggerSpy)
        isolated.setattr("structlog.configure", lambda **_kwargs: None)
        configure_logging(level="DEBUG", format_name="json")

    assert configured_levels == {
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "aio_pika": logging.WARNING,
        "aiormq": logging.WARNING,
    }
