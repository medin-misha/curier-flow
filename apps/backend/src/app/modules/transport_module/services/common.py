"""Нормализация, общие проверки и преобразование DB-конфликтов."""

from decimal import Decimal
from typing import NoReturn

from sqlalchemy.exc import IntegrityError

from app.kernel.errors import Conflict, NotFound, ValidationFailed

_MAX_SHORT_LENGTH = 64


def normalize_transport_type(value: str) -> str:
    """Нормализовать строковый тип для сервисов и list-фильтров."""
    normalized = value.strip().lower()
    if not normalized or len(normalized) > _MAX_SHORT_LENGTH:
        raise ValidationFailed("Invalid transport type", reason="invalid-transport-type")
    return normalized


def normalize_serial_number(value: str) -> str:
    """Нормализовать серийный номер перед записью или поиском."""
    normalized = value.strip().upper()
    if not normalized or len(normalized) > _MAX_SHORT_LENGTH:
        raise ValidationFailed("Invalid serial number", reason="invalid-serial-number")
    return normalized


def normalize_trimmed(value: str, *, field: str, maximum: int) -> str:
    """Убрать внешние пробелы и проверить непустое ограниченное поле."""
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValidationFailed(f"Invalid {field}", reason=f"invalid-{field.replace('_', '-')}")
    return normalized


def validate_deposit(required: bool, amount: Decimal | None) -> None:
    """Проверить согласованность признака и суммы залога."""
    if required != (amount is not None):
        raise ValidationFailed(
            "deposit_amount is required exactly when deposit_required is true",
            reason="invalid-deposit-state",
        )


def raise_known_integrity(error: IntegrityError) -> NoReturn:
    """Преобразовать только известные transport constraints в AppError."""
    constraint = constraint_name(error)
    if constraint == "uq_transports_serial_number":
        raise Conflict("Serial number already exists", reason="duplicate-serial-number") from error
    if constraint == "uq_transport_components_transport_id_name":
        raise Conflict("Component name already exists", reason="duplicate-component") from error
    if constraint == "excl_courier_transports_transport_period":
        raise Conflict(
            "Transport rental periods overlap", reason="transport-rental-overlap"
        ) from error
    if constraint == "excl_courier_transports_courier_period":
        raise Conflict("Courier rental periods overlap", reason="courier-rental-overlap") from error
    if constraint == "uq_courier_transports_file_id":
        raise Conflict(
            "File is already attached to a rental", reason="contract-file-in-use"
        ) from error
    if constraint == "fk_courier_transports_courier_id_couriers":
        raise NotFound("Courier not found", resource="Courier") from error
    if constraint == "contract_file_not_ready":
        raise ValidationFailed("Contract file is not ready", reason="file-not-ready") from error
    if constraint == "signed_contract_protects_rental":
        raise Conflict(
            "A signed contract prevents deleting this rental",
            reason="signed-contract-protects-rental",
        ) from error
    raise error


def constraint_name(error: IntegrityError) -> str | None:
    """Достать имя PostgreSQL constraint из цепочки asyncpg adapter."""
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
