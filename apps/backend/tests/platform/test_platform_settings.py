"""Настройки платформы читаются из тех переменных, что описаны в .env.example.

Проверка не про pydantic, а про имена: `env_prefix` и поле складываются в имя
переменной, и опечатка в любой половине даёт молча работающий дефолт вместо
настройки из окружения. Такое обнаруживается только в проде.
"""

from pathlib import Path
from typing import Any

import pytest

import app
from app.platform.rabbitmq import RabbitMQSettings
from app.platform.s3 import S3Settings
from app.platform.taskiq import RedisSettings
from app.worker import WorkerSettings

ENV_EXAMPLE = Path(app.__file__).resolve().parents[2] / ".env.example"

#: Переменная в .env.example → как она должна прочитаться классом настроек.
EXPECTED: dict[str, tuple[type[Any], str, Any]] = {
    "RABBITMQ_DSN": (RabbitMQSettings, "dsn", "amqp://guest:guest@localhost:5672/"),
    "RABBITMQ_MAX_RETRIES": (RabbitMQSettings, "max_retries", 5),
    "REDIS_DSN": (RedisSettings, "dsn", "redis://localhost:6379/0"),
    "REDIS_RESULT_TTL": (RedisSettings, "result_ttl", 86400),
    "S3_ENDPOINT_URL": (S3Settings, "endpoint_url", "http://localhost:9000"),
    "S3_REGION": (S3Settings, "region", "us-east-1"),
    "S3_ACCESS_KEY": (S3Settings, "access_key", "minioadmin"),
    "S3_SECRET_KEY": (S3Settings, "secret_key", "minioadmin"),
    "S3_BUCKET": (S3Settings, "bucket", "app-files"),
    "S3_PRESIGN_TTL": (S3Settings, "presign_ttl", 900),
    "WORKER_SHUTDOWN_TIMEOUT": (WorkerSettings, "shutdown_timeout", 30.0),
    "WORKER_MAX_CONCURRENT_TASKS": (WorkerSettings, "max_concurrent_tasks", 10),
}


def documented_variables() -> set[str]:
    """Имена переменных, объявленных в .env.example."""
    return {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def test_every_checked_variable_is_documented() -> None:
    assert set(EXPECTED) <= documented_variables()


@pytest.mark.parametrize(("variable", "expectation"), sorted(EXPECTED.items()))
def test_variable_is_read_by_its_settings_class(
    variable: str,
    expectation: tuple[type[Any], str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_class, field, value = expectation
    # Переменная из окружения разработчика перебила бы файл: тест проверяет
    # именно связь «имя в .env.example ↔ поле класса».
    monkeypatch.delenv(variable, raising=False)

    settings = settings_class(_env_file=ENV_EXAMPLE)

    assert str(getattr(settings, field)) == str(value)
