"""Безопасные ответы административного модуля."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.kernel.schemas import BaseResponse


class AdminResponse(BaseResponse):
    """Администратор без password hash и внутренних версий."""

    id: UUID
    username: str
    telegram_id: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccessTokenResponse(BaseResponse):
    """Access JWT; refresh передаётся только HttpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  # OAuth token type, не секрет
    expires_in: int
