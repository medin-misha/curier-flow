"""Тесты plain-text formatter и platform display mapping."""

import json

import pytest

from conftest import VALID_PAYLOAD
from telegram_bot.contracts import CourierRegistrationNotification
from telegram_bot.rendering import render_notification


def payload(**changes: object) -> CourierRegistrationNotification:
    """Построить валидный payload с отдельными изменениями."""
    raw = {**VALID_PAYLOAD, **changes}
    return CourierRegistrationNotification.model_validate_json(json.dumps(raw))


def test_plain_text_notification() -> None:
    """Formatter выдаёт точный readable plain text."""
    assert render_notification(payload()) == (
        "Новая регистрация курьера\nИмя: Jan Novak\nКонтакт: telegram — @jan\nПлатформа: Wolt"
    )


@pytest.mark.parametrize(
    ("platform", "display"),
    [
        ("bolt_food", "Bolt Food"),
        ("foodora", "Foodora"),
        ("wolt", "Wolt"),
    ],
)
def test_platform_display_mapping(platform: str, display: str) -> None:
    """Каждое контрактное значение имеет product display name."""
    assert render_notification(payload(platform=platform)).endswith(f"Платформа: {display}")


@pytest.mark.parametrize(
    ("contact_platform", "contact"),
    [(None, "@jan"), ("telegram", None), (None, None)],
)
def test_missing_contact_uses_fallback(
    contact_platform: str | None,
    contact: str | None,
) -> None:
    """Неполный contact не отбрасывает notification."""
    text = render_notification(payload(contact_platform=contact_platform, contact=contact))

    assert "Контакт: не указан" in text


def test_user_markup_remains_literal_text() -> None:
    """Formatter не добавляет Markdown/HTML и сохраняет данные буквально."""
    text = render_notification(
        payload(full_name="<b>Jan</b> *admin*", contact="https://example.test")
    )

    assert "Имя: <b>Jan</b> *admin*" in text
    assert "https://example.test" in text
