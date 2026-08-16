"""Транспортные middleware: контекст запроса, тайминг, лог доступа.

Здесь только транспорт. Аутентификация, лимиты и бизнес-проверки в middleware
не живут: middleware выполняется для каждого запроса, включая те, к которым
правило не относится, и отладка «почему ручка отвечает 403» начинается с
чтения всей цепочки вместо кода ручки.

Реализация — «сырое» ASGI-приложение, а не `BaseHTTPMiddleware`: последний
исполняет остальную цепочку в отдельной задаче, из-за чего contextvars,
выставленные вокруг вызова, ведут себя не так, как написано в коде.
"""

import re
import time
from http import HTTPStatus
from typing import Final

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uuid_utils.compat import uuid7

from app.kernel.context import request_id

#: Имя заголовка в нижнем регистре: в ASGI заголовки приходят нормализованными.
REQUEST_ID_HEADER: Final = "x-request-id"

#: Чужой идентификатор попадает и в логи, и в заголовок ответа, поэтому
#: принимается только короткое значение из безопасных символов. Иначе клиент
#: управляет содержимым наших логов и может подмешать в них что угодно.
_SAFE_REQUEST_ID: Final = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_logger = structlog.get_logger("app.api.access")


class RequestContextMiddleware:
    """Заводит контекст запроса и пишет по одной строке лога на запрос."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        current_id = _resolve_request_id(Headers(scope=scope))
        # Токен намеренно не сбрасывается на выходе: ответ 500 формирует
        # ServerErrorMiddleware — снаружи этого middleware, и сброшенный
        # идентификатор не попал бы ни в тело problem+json, ни в его лог.
        # Контекст запроса живёт в своей задаче и между запросами не течёт.
        request_id.set(current_id)

        # Если исключение дойдёт до сервера, ответом будет 500: строка лога
        # должна сказать то же самое, что увидел клиент.
        status = HTTPStatus.INTERNAL_SERVER_ERROR.value
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                # setdefault, а не append: обработчики ошибок ставят заголовок
                # сами, и дубль в ответе выглядел бы как два разных запроса.
                MutableHeaders(scope=message).setdefault(REQUEST_ID_HEADER, current_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _log_request(scope, status=status, elapsed=time.perf_counter() - started)


def _resolve_request_id(headers: Headers) -> str:
    """Взять идентификатор из заголовка запроса или сгенерировать новый.

    UUIDv7: он монотонен по времени, поэтому строки лога, отсортированные по
    идентификатору, идут в порядке поступления запросов.
    """
    incoming = headers.get(REQUEST_ID_HEADER)
    if incoming is not None and _SAFE_REQUEST_ID.match(incoming):
        return incoming
    return str(uuid7())


def _log_request(scope: Scope, *, status: int, elapsed: float) -> None:
    """Записать итог запроса. Строка ровно одна, поля одинаковые для всех."""
    log = _logger.error if status >= HTTPStatus.INTERNAL_SERVER_ERROR else _logger.info
    log(
        "http.request",
        method=scope["method"],
        # Только путь: query-string попадает в логи целиком, а в ней бывают
        # токены и персональные данные.
        path=scope["path"],
        status=status,
        duration_ms=round(elapsed * 1000, 3),
    )
