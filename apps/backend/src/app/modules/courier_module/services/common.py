"""Общие проверки и преобразование ошибок courier-сервисов."""

import re
from typing import NoReturn

from sqlalchemy.exc import IntegrityError

from app.kernel.errors import Conflict, ValidationFailed

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
_PHONE_FORMATTING = str.maketrans("", "", " -()")
_MAX_EMAIL_LENGTH = 320


def normalize_email(value: str) -> str:
    """Нормализовать и проверить email natural key."""
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > _MAX_EMAIL_LENGTH
        or _EMAIL.fullmatch(normalized) is None
    ):
        raise ValidationFailed("Invalid email", reason="invalid-email")
    return normalized


def normalize_phone(value: str) -> str:
    """Убрать разрешённое форматирование и проверить строгий E.164."""
    normalized = value.translate(_PHONE_FORMATTING)
    if _PHONE.fullmatch(normalized) is None:
        raise ValidationFailed("Invalid phone", reason="invalid-phone")
    return normalized


def raise_known_integrity(error: IntegrityError) -> NoReturn:
    """Преобразовать только известные именованные DB-конфликты."""
    constraint = _constraint_name(error)
    if constraint == "uq_couriers_email":
        raise Conflict("Email already belongs to another courier", field="email") from error
    if constraint == "uq_couriers_phone":
        raise Conflict("Phone already belongs to another courier", field="phone") from error
    if constraint == "uq_courier_platform_accounts_courier_id_platform":
        raise Conflict("Courier already has this platform", reason="duplicate-platform") from error
    if constraint in {"signed_contract_protects_rental", "file_deletion_protected"}:
        raise Conflict(
            "A signed contract prevents deleting this courier",
            reason="signed-contract-protects-rental",
        ) from error
    raise error


def _constraint_name(error: IntegrityError) -> str | None:
    """Достать имя Postgres constraint из asyncpg adapter chain."""
    original = error.orig
    candidates = (
        original,
        original.__cause__ if original is not None else None,
        original.__context__ if original is not None else None,
    )
    for candidate in candidates:
        if candidate is None:
            continue
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name
        diag = getattr(candidate, "diag", None)
        name = getattr(diag, "constraint_name", None)
        if isinstance(name, str):
            return name
    return None
