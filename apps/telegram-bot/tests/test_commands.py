"""Команды /start через локальный Telegram API stub."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from telegram_bot.commands import poll_start_commands
from telegram_bot.config import Settings
from telegram_bot.telegram import TelegramAuthError, TelegramBotClient
from telegram_bot.worker import run_service


@pytest.mark.parametrize(
    ("text", "chat_id", "should_reply"),
    [
        ("/start", 123456789, True),
        ("/start invite", 123456789, True),
        ("/start@Courier_Bot", -100123456789, True),
        ("/start@courier_bot invite", -100123456789, True),
        ("/start@other_bot", -100123456789, False),
        ("/starter", 123456789, False),
        ("hello", 123456789, False),
        ("", 123456789, False),
    ],
)
async def test_start_replies_with_current_chat_and_advances_offset(
    text: str, chat_id: int, should_reply: bool
) -> None:
    """Ответ содержит ID чата, включая отрицательный ID группы, а не ID отправителя."""
    requests: list[tuple[str, dict[str, Any]]] = []
    stop_event = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = request.url.path.rsplit("/", maxsplit=1)[-1]
        requests.append((method, payload))
        if method == "getUpdates" and "offset" not in payload:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 41,
                            "message": {
                                "text": text,
                                "chat": {"id": chat_id},
                                "from": {"id": 999},
                            },
                        }
                    ],
                },
            )
        if method == "getUpdates":
            stop_event.set()
            return httpx.Response(200, json={"ok": True, "result": []})
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with TelegramBotClient(
        token=SecretStr("stub-token"), timeout=1, transport=httpx.MockTransport(handle)
    ) as telegram:
        telegram.username = "courier_bot"
        await poll_start_commands(telegram, stop_event)

    assert requests[0] == ("getUpdates", {"timeout": 20, "allowed_updates": ["message"]})
    assert requests[-1] == (
        "getUpdates",
        {"timeout": 20, "allowed_updates": ["message"], "offset": 42},
    )
    replies = [payload for method, payload in requests if method == "sendMessage"]
    assert replies == (
        [
            {
                "chat_id": chat_id,
                "text": f"chat_id: {chat_id}",
                "link_preview_options": {"is_disabled": True},
            }
        ]
        if should_reply
        else []
    )


async def test_polling_auth_failure_closes_worker_before_rabbitmq_is_ready() -> None:
    """Ошибки token в polling останавливают startup и закрывают HTTP client."""

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "courier_bot"}})
        return httpx.Response(401, json={"ok": False, "error_code": 401})

    async def wait_for_rabbit(_settings: Settings) -> Any:
        await asyncio.Event().wait()

    telegram = TelegramBotClient(
        token=SecretStr("stub-token"), timeout=1, transport=httpx.MockTransport(handle)
    )
    with pytest.raises(TelegramAuthError):
        await asyncio.wait_for(
            run_service(
                Settings(_env_file=None, telegram_bot_token="stub-token"),
                stop_event=asyncio.Event(),
                connection_opener=wait_for_rabbit,
                telegram_factory=lambda _settings: telegram,
            ),
            timeout=1,
        )
    assert telegram._client.is_closed


@pytest.mark.parametrize("status", [400, 429, 500])
async def test_reply_failure_skips_permanent_error_and_retries_transient_error(status: int) -> None:
    """Permanent ошибка продвигает offset, временная повторяет тот же update."""
    stop_event = asyncio.Event()
    offsets: list[int | None] = []
    reply_attempts = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal reply_attempts
        payload = json.loads(request.content)
        if request.url.path.endswith("/sendMessage"):
            reply_attempts += 1
            if reply_attempts == 1:
                return httpx.Response(
                    status,
                    json={"ok": False, "error_code": status, "parameters": {"retry_after": 1}},
                )
            return httpx.Response(200, json={"ok": True, "result": {}})
        offsets.append(payload.get("offset"))
        if payload.get("offset") == 42:
            stop_event.set()
            return httpx.Response(200, json={"ok": True, "result": []})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [{"update_id": 41, "message": {"text": "/start", "chat": {"id": 1}}}],
            },
        )

    async with TelegramBotClient(
        token=SecretStr("stub-token"), timeout=1, transport=httpx.MockTransport(handle)
    ) as telegram:
        await poll_start_commands(telegram, stop_event)

    assert offsets == ([None, 42] if status == 400 else [None, None, 42])
    assert reply_attempts == (1 if status == 400 else 2)
