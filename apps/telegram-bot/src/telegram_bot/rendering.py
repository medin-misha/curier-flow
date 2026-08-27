"""Безопасный plain-text formatter Telegram-сообщения."""

from typing import Final

from telegram_bot.contracts import CourierRegistrationNotification, Platform

PLATFORM_DISPLAY: Final[dict[Platform, str]] = {
    "bolt_food": "Bolt Food",
    "foodora": "Foodora",
    "wolt": "Wolt",
}


def render_notification(payload: CourierRegistrationNotification) -> str:
    """Отрендерить пользовательские данные без markup-интерпретации."""
    if payload.contact_platform is None or payload.contact is None:
        contact = "не указан"
    else:
        contact = f"{payload.contact_platform} — {payload.contact}"

    return "\n".join(
        (
            "Новая регистрация курьера",
            f"Имя: {payload.full_name}",
            f"Контакт: {contact}",
            f"Платформа: {PLATFORM_DISPLAY[payload.platform]}",
        )
    )
