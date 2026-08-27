"""Общие fakes и локальный HTTP stub для тестов."""

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from telegram_bot.rabbitmq import CONTENT_TYPE, ROUTING_KEY

MESSAGE_ID = str(UUID("e9381839-348d-4192-a738-c495bfcae19f"))
VALID_PAYLOAD = {
    "telegram_id": 123456789,
    "full_name": "Jan Novak",
    "contact_platform": "telegram",
    "contact": "@jan",
    "platform": "wolt",
}


class FakeIncomingMessage:
    """Минимальный duck-typed AbstractIncomingMessage."""

    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str | None = CONTENT_TYPE,
        message_id: str | None = MESSAGE_ID,
        routing_key: str | None = ROUTING_KEY,
        headers: dict[str, Any] | None = None,
        events: list[str] | None = None,
        ack_error: Exception | None = None,
    ) -> None:
        selected_payload = VALID_PAYLOAD if payload is None else payload
        self.body = body if body is not None else json.dumps(selected_payload).encode()
        self.content_type = content_type
        self.message_id = message_id
        self.routing_key = routing_key
        self.headers = {} if headers is None else headers
        self.content_encoding = None
        self.priority = None
        self.correlation_id = "correlation-id"
        self.reply_to = None
        self.timestamp = None
        self.type = "domain-event"
        self.app_id = "backend"
        self.events = [] if events is None else events
        self.ack_error = ack_error
        self.acked = False
        self.rejected = False
        self.requeue: bool | None = None

    async def ack(self) -> None:
        """Записать ACK либо имитировать разрыв до подтверждения."""
        self.events.append("ack")
        if self.ack_error is not None:
            raise self.ack_error
        self.acked = True

    async def reject(self, *, requeue: bool) -> None:
        """Записать reject, который RabbitMQ маршрутизирует в DLQ."""
        self.events.append("reject")
        self.rejected = True
        self.requeue = requeue


@dataclass(frozen=True, slots=True)
class StubRequest:
    """Запрос, принятый локальным Telegram stub."""

    path: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StubResponse:
    """Запланированный JSON response локального Telegram stub."""

    status: int
    payload: dict[str, Any]


class TelegramStubServer:
    """Минимальный HTTP/1.1 server без внешней сети."""

    def __init__(self) -> None:
        self.responses: deque[StubResponse] = deque()
        self.requests: list[StubRequest] = []
        self._server: asyncio.Server | None = None

    @property
    def base_url(self) -> str:
        """Вернуть loopback URL запущенного server."""
        if self._server is None or not self._server.sockets:
            raise RuntimeError("stub server is not started")
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def enqueue(self, status: int, payload: dict[str, Any]) -> None:
        """Добавить следующий JSON response."""
        self.responses.append(StubResponse(status=status, payload=payload))

    async def start(self) -> None:
        """Открыть случайный loopback port."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def close(self) -> None:
        """Закрыть listening socket."""
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Принять один POST и закрыть соединение после ответа."""
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            request_line, *header_lines = head.decode("ascii").split("\r\n")
            _, path, _ = request_line.split(" ", maxsplit=2)
            headers = {
                name.lower(): value.strip()
                for line in header_lines
                if ":" in line
                for name, value in (line.split(":", maxsplit=1),)
            }
            content_length = int(headers.get("content-length", "0"))
            body = await reader.readexactly(content_length)
            request_payload = json.loads(body) if body else {}
            self.requests.append(StubRequest(path=path, payload=request_payload))

            response = (
                self.responses.popleft()
                if self.responses
                else StubResponse(status=200, payload={"ok": True, "result": {}})
            )
            encoded = json.dumps(response.payload).encode()
            reason = "OK" if response.status == 200 else "Error"
            writer.write(
                (
                    f"HTTP/1.1 {response.status} {reason}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(encoded)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
                + encoded
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.fixture
async def telegram_stub() -> AsyncIterator[TelegramStubServer]:
    """Предоставить локальный Telegram API stub."""
    server = TelegramStubServer()
    await server.start()
    try:
        yield server
    finally:
        await server.close()
