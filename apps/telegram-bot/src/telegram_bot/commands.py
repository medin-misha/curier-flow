"""Обработка /start без привязки пользователей к backend."""

import asyncio
from contextlib import suppress
from typing import Any

import structlog

from telegram_bot.telegram import (
    TelegramBotClient,
    TelegramNetworkError,
    TelegramPermanentError,
    TelegramRateLimitError,
    TelegramTransientError,
)

_logger = structlog.get_logger("telegram_bot.commands")


async def poll_start_commands(telegram: TelegramBotClient, stop_event: asyncio.Event) -> None:
    """Ответить chat_id текущего чата и подтвердить обработанные updates."""
    offset: int | None = None
    while not stop_event.is_set():
        try:
            updates = await telegram.get_updates(offset=offset)
            for update in updates:
                if stop_event.is_set():
                    return
                update_id = update.get("update_id")
                if not isinstance(update_id, int) or isinstance(update_id, bool):
                    continue
                chat_id = _start_chat_id(update, bot_username=telegram.username)
                if chat_id is not None:
                    try:
                        await telegram.send_message(telegram_id=chat_id, text=f"chat_id: {chat_id}")
                    except TelegramPermanentError as error:
                        _logger.warning(
                            "telegram.command_reply_rejected", telegram_status=error.status_code
                        )
                offset = update_id + 1
        except (TelegramNetworkError, TelegramTransientError) as error:
            delay = error.retry_after if isinstance(error, TelegramRateLimitError) else 1
            _logger.warning(
                "telegram.command_poll_retry",
                telegram_status=error.status_code,
                error_class=type(error).__name__,
                delay=max(delay, 1),
            )
            with suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=max(delay, 1))


def _start_chat_id(update: dict[str, Any], *, bot_username: str | None) -> int | None:
    """Распознать /start, его аргументы и команду с username этого бота."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("text")
    chat = message.get("chat")
    if not isinstance(text, str) or not isinstance(chat, dict):
        return None
    parts = text.split(maxsplit=1)
    if not parts:
        return None
    command, separator, target = parts[0].partition("@")
    if command != "/start":
        return None
    if separator and (bot_username is None or target.lower() != bot_username.lower()):
        return None
    chat_id = chat.get("id")
    return chat_id if isinstance(chat_id, int) and not isinstance(chat_id, bool) else None
