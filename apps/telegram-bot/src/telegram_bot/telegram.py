"""Минимальный асинхронный клиент Telegram Bot API."""

from typing import Any, Final

import httpx
from pydantic import SecretStr

TELEGRAM_API_BASE_URL: Final = "https://api.telegram.org"
HTTP_OK: Final = 200
HTTP_BAD_REQUEST: Final = 400
HTTP_UNAUTHORIZED: Final = 401
HTTP_TOO_MANY_REQUESTS: Final = 429
HTTP_INTERNAL_SERVER_ERROR: Final = 500


class TelegramError(Exception):
    """Безопасная базовая ошибка без response body и URL с токеном."""

    def __init__(self, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(type(self).__name__)


class TelegramNetworkError(TelegramError):
    """Сетевая или transport-ошибка, которую можно повторить."""


class TelegramTransientError(TelegramError):
    """Временная ошибка Telegram или неожиданный ответ API."""


class TelegramPermanentError(TelegramError):
    """Постоянная 4xx-ошибка конкретного назначения."""


class TelegramAuthError(TelegramError):
    """Ошибка bot token, которая должна остановить consumer."""


class TelegramRateLimitError(TelegramTransientError):
    """Ограничение частоты с серверной длительностью паузы."""

    def __init__(self, *, retry_after: int, status_code: int = 429) -> None:
        self.retry_after = retry_after
        super().__init__(status_code=status_code)


class TelegramBotClient:
    """HTTP-клиент только для getMe и plain-text sendMessage."""

    def __init__(
        self,
        *,
        token: SecretStr,
        timeout: float,
        base_url: str = TELEGRAM_API_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    async def __aenter__(self) -> "TelegramBotClient":
        """Вернуть открытый клиент."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Закрыть HTTP connection pool."""
        await self.aclose()

    async def aclose(self) -> None:
        """Закрыть HTTP connection pool."""
        await self._client.aclose()

    async def get_me(self) -> None:
        """Проверить bot token до подключения consumer."""
        await self._call("getMe", {})

    async def send_message(self, *, telegram_id: int, text: str) -> None:
        """Отправить plain text с отключённым preview ссылок."""
        await self._call(
            "sendMessage",
            {
                "chat_id": telegram_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
            },
        )

    async def _call(self, method: str, payload: dict[str, Any]) -> None:
        """Выполнить Bot API вызов и классифицировать безопасную ошибку."""
        token = self._token.get_secret_value()
        url = f"{self._base_url}/bot{token}/{method}"
        try:
            response = await self._client.post(url, json=payload)
        except httpx.TransportError:
            # Не сохраняем исходное исключение: его URL содержит bot token.
            raise TelegramNetworkError() from None

        response_payload = _response_payload(response)
        if response.status_code == HTTP_OK and response_payload.get("ok") is True:
            return

        status_code = _error_code(response.status_code, response_payload)
        if status_code == HTTP_UNAUTHORIZED:
            raise TelegramAuthError(status_code=status_code)
        if status_code == HTTP_TOO_MANY_REQUESTS:
            raise TelegramRateLimitError(
                retry_after=_retry_after(response_payload),
                status_code=status_code,
            )
        if HTTP_BAD_REQUEST <= status_code < HTTP_INTERNAL_SERVER_ERROR:
            raise TelegramPermanentError(status_code=status_code)
        raise TelegramTransientError(status_code=status_code)


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    """Разобрать JSON, не сохраняя сырой Telegram response."""
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _error_code(http_status: int, payload: dict[str, Any]) -> int:
    """Предпочесть Telegram error_code корректного целого типа."""
    error_code = payload.get("error_code")
    if isinstance(error_code, int) and not isinstance(error_code, bool):
        return error_code
    return http_status


def _retry_after(payload: dict[str, Any]) -> int:
    """Вернуть неотрицательный retry_after из Telegram parameters."""
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        return 0
    retry_after = parameters.get("retry_after")
    if not isinstance(retry_after, int) or isinstance(retry_after, bool):
        return 0
    return max(retry_after, 0)
