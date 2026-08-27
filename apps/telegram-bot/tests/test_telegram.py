"""Contract-тесты Telegram Bot API client через локальный stub."""

from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from telegram_bot.telegram import (
    TelegramAuthError,
    TelegramBotClient,
    TelegramNetworkError,
    TelegramPermanentError,
    TelegramRateLimitError,
    TelegramTransientError,
)


async def test_get_me_uses_stub_api(telegram_stub: Any) -> None:
    """getMe проверяет token без реального Telegram network."""
    telegram_stub.enqueue(200, {"ok": True, "result": {"id": 1}})
    client = TelegramBotClient(
        token=SecretStr("stub-token"),
        timeout=1,
        base_url=telegram_stub.base_url,
    )

    async with client:
        await client.get_me()

    assert telegram_stub.requests[0].path == "/botstub-token/getMe"
    assert telegram_stub.requests[0].payload == {}


async def test_send_message_is_plain_text_without_parse_mode(telegram_stub: Any) -> None:
    """sendMessage отключает preview и не включает markup mode."""
    telegram_stub.enqueue(200, {"ok": True, "result": {"message_id": 10}})
    client = TelegramBotClient(
        token=SecretStr("stub-token"),
        timeout=1,
        base_url=telegram_stub.base_url,
    )

    async with client:
        await client.send_message(telegram_id=123, text="<b>literal</b> *plain*")

    request = telegram_stub.requests[0]
    assert request.path == "/botstub-token/sendMessage"
    assert request.payload == {
        "chat_id": 123,
        "text": "<b>literal</b> *plain*",
        "link_preview_options": {"is_disabled": True},
    }
    assert "parse_mode" not in request.payload


@pytest.mark.parametrize(
    ("status", "payload", "error_type"),
    [
        (401, {"ok": False, "error_code": 401}, TelegramAuthError),
        (400, {"ok": False, "error_code": 400}, TelegramPermanentError),
        (403, {"ok": False, "error_code": 403}, TelegramPermanentError),
        (500, {"ok": False, "error_code": 500}, TelegramTransientError),
        (503, {"ok": False}, TelegramTransientError),
    ],
)
async def test_http_errors_are_classified(
    telegram_stub: Any,
    status: int,
    payload: dict[str, Any],
    error_type: type[Exception],
) -> None:
    """401, permanent 4xx и transient 5xx имеют разные классы."""
    telegram_stub.enqueue(status, payload)
    client = TelegramBotClient(
        token=SecretStr("stub-token"),
        timeout=1,
        base_url=telegram_stub.base_url,
    )

    async with client:
        with pytest.raises(error_type):
            await client.send_message(telegram_id=123, text="plain")


async def test_telegram_error_code_is_used_for_ok_false(telegram_stub: Any) -> None:
    """Даже HTTP 200 с Telegram error_code классифицируется как failure."""
    telegram_stub.enqueue(200, {"ok": False, "error_code": 403})
    client = TelegramBotClient(
        token=SecretStr("stub-token"),
        timeout=1,
        base_url=telegram_stub.base_url,
    )

    async with client:
        with pytest.raises(TelegramPermanentError):
            await client.send_message(telegram_id=123, text="plain")


async def test_retry_after_is_parsed(telegram_stub: Any) -> None:
    """429 переносит server-provided retry_after в безопасную ошибку."""
    telegram_stub.enqueue(
        429,
        {"ok": False, "error_code": 429, "parameters": {"retry_after": 47}},
    )
    client = TelegramBotClient(
        token=SecretStr("stub-token"),
        timeout=1,
        base_url=telegram_stub.base_url,
    )

    async with client:
        with pytest.raises(TelegramRateLimitError) as raised:
            await client.send_message(telegram_id=123, text="plain")

    assert raised.value.retry_after == 47
    assert raised.value.status_code == 429


async def test_transport_error_does_not_expose_token() -> None:
    """Transport exception преобразуется без URL и token в exception chain."""
    raw_token = "stub-secret-token"

    async def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("stub unavailable", request=request)

    client = TelegramBotClient(
        token=SecretStr(raw_token),
        timeout=1,
        transport=httpx.MockTransport(fail),
    )

    async with client:
        with pytest.raises(TelegramNetworkError) as raised:
            await client.get_me()

    assert raw_token not in str(raised.value)
    assert raw_token not in repr(raised.value)
    assert raised.value.__cause__ is None
