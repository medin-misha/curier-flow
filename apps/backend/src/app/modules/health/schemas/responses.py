"""Схемы ответов модуля health.

Файла `requests.py` рядом нет: ни одна ручка модуля не принимает ни тела, ни
параметров. Пустая схема запроса была бы заглушкой, а не контрактом.
"""

from typing import Literal

from app.kernel.schemas import BaseResponse

#: Состояние зависимости. Строка, а не bool: в ответе, который читают глазами
#: и грепают в логах, "down" однозначнее, чем `false` рядом с полем `status`.
DependencyState = Literal["up", "down"]


class LivenessResponse(BaseResponse):
    """Ответ `/health/live`."""

    status: Literal["alive"]


class DependencyReport(BaseResponse):
    """Состояние одной зависимости в отчёте готовности."""

    name: str
    status: DependencyState
    duration_ms: float
    error: str | None


class ReadinessResponse(BaseResponse):
    """Отчёт `/health/ready`: сводный вердикт и детализация по зависимостям.

    Обычная схема ответа, а не problem+json: неготовность — это отчёт о
    состоянии, а не ошибка обращения. Клиент здесь не ошибся и исправлять ему
    нечего, а детализация по зависимостям в problem+json уехала бы в
    произвольные дополнительные члены, которых нет ни в схеме, ни в OpenAPI.
    """

    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyReport]


class InfoResponse(BaseResponse):
    """Ответ `/health/info`: что за сервис отвечает по этому адресу.

    Только то, что помогает опознать сборку. Ни DSN, ни ключей, ни имён хостов
    зависимостей: ручка отвечает без аутентификации, и всё, что в ней есть,
    считается опубликованным.
    """

    name: str
    version: str
    environment: str
    revision: str | None
