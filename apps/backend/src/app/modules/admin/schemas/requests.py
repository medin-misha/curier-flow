"""Входные схемы администраторов и аутентификации."""

import re
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.kernel.schemas import BaseRequest

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,64}$")
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=USERNAME_PATTERN.pattern),
]
Password = Annotated[
    str,
    StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
]


class AdminCreate(BaseRequest):
    """Новая административная учётная запись."""

    username: Username
    password: Password
    telegram_id: int | None = Field(default=None, gt=0)


class AdminLogin(BaseRequest):
    """Credentials входа администратора."""

    username: Username
    password: Password


class AdminPatch(BaseRequest):
    """Частичное изменение публичных полей Admin."""

    username: Username | None = None
    telegram_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _forbid_null_username(self) -> Self:
        """Разрешить очистку Telegram ID, но не обязательного username."""
        if "username" in self.model_fields_set and self.username is None:
            raise ValueError("Fields must not be null: username")
        return self


class AdminPasswordReset(BaseRequest):
    """Новый пароль выбранного администратора."""

    new_password: Password


def normalize_username(value: str) -> str:
    """Нормализовать и проверить username вне HTTP-схем, например bootstrap."""
    normalized = value.strip().lower()
    if USERNAME_PATTERN.fullmatch(normalized) is None:
        raise ValueError("username must match [a-z0-9._-]{3,64}")
    return normalized


def validate_password(value: str) -> str:
    """Проверить длину bootstrap-пароля без включения значения в ошибку."""
    if not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
        raise ValueError("password length must be between 12 and 128 characters")
    return value
