"""Тесты exact пяти-полевого payload."""

import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import VALID_PAYLOAD
from telegram_bot.contracts import SIGNED_INT64_MAX, CourierRegistrationNotification


def validate(payload: dict[str, Any]) -> CourierRegistrationNotification:
    """Проверить объект именно через JSON transport path."""
    return CourierRegistrationNotification.model_validate_json(json.dumps(payload))


def test_exact_payload_is_accepted() -> None:
    """Все пять полей разбираются без backend imports."""
    payload = validate(VALID_PAYLOAD)

    assert set(payload.model_dump()) == {
        "telegram_id",
        "full_name",
        "contact_platform",
        "contact",
        "platform",
    }
    assert payload.telegram_id == 123456789
    assert payload.platform == "wolt"


def test_nullable_contacts_are_accepted() -> None:
    """Оба contact-поля могут независимо быть null."""
    payload = deepcopy(VALID_PAYLOAD)
    payload["contact_platform"] = None
    payload["contact"] = None

    validated = validate(payload)

    assert validated.contact_platform is None
    assert validated.contact is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telegram_id", 0),
        ("telegram_id", -1),
        ("telegram_id", SIGNED_INT64_MAX + 1),
        ("telegram_id", "123"),
        ("telegram_id", True),
        ("full_name", ""),
        ("full_name", "x" * 256),
        ("full_name", 123),
        ("contact_platform", "x" * 33),
        ("contact", "x" * 256),
        ("platform", "bolt"),
        ("platform", 1),
    ],
)
def test_invalid_or_coerced_values_are_rejected(field: str, value: Any) -> None:
    """Ограничения длины, enum и строгих типов не расширяются."""
    payload = deepcopy(VALID_PAYLOAD)
    payload[field] = value

    with pytest.raises(ValidationError):
        validate(payload)


def test_missing_and_extra_fields_are_rejected() -> None:
    """Contract нельзя молчаливо расширить или сократить."""
    missing = deepcopy(VALID_PAYLOAD)
    del missing["contact"]
    extra = {**VALID_PAYLOAD, "admin_id": "private"}

    with pytest.raises(ValidationError):
        validate(missing)
    with pytest.raises(ValidationError):
        validate(extra)
