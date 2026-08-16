"""Иерархия прикладных ошибок.

Бизнес-код не должен знать о транспорте: сервис одинаково вызывается из HTTP
хендлера, консьюмера RabbitMQ и задачи TaskIQ, а `HTTPException` осмысленна
только в первом случае. Поэтому ошибки описаны здесь без единой ссылки на
веб-фреймворк, а перевод в RFC 9457 problem+json делает слой `api`.

Каждый класс несёт три атрибута класса: `code` — стабильный машинный
идентификатор для клиента, `status` — HTTP-статус, в который ошибку переведёт
API, `title` — короткое человекочитаемое название типа проблемы.
"""

from typing import Any, ClassVar


class AppError(Exception):
    """Базовая прикладная ошибка.

    Наследники переопределяют `code`, `status` и `title`. Дефолты соответствуют
    неопознанному сбою: если наследник забыл их выставить, ответ будет 500,
    а не падение обработчика ошибок на отсутствующем атрибуте.

    Принимает необязательный `detail` — пояснение для конкретного случая, и
    произвольные именованные поля `extra`, которые API кладёт в problem+json
    дополнительными членами (например, список запрещённых полей).
    """

    code: ClassVar[str] = "internal-error"
    status: ClassVar[int] = 500
    title: ClassVar[str] = "Internal Server Error"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)


class NotFound(AppError):
    """Запрошенного ресурса не существует или он недоступен этому клиенту."""

    code = "not-found"
    status = 404
    title = "Not Found"


class Conflict(AppError):
    """Запрос противоречит текущему состоянию ресурса или его инвариантам."""

    code = "conflict"
    status = 409
    title = "Conflict"


class ValidationFailed(AppError):
    """Данные синтаксически разобраны, но не проходят проверку по смыслу."""

    code = "validation-failed"
    status = 422
    title = "Validation Failed"


class PermissionDenied(AppError):
    """Клиент опознан, но выполнять эту операцию ему не разрешено."""

    code = "permission-denied"
    status = 403
    title = "Forbidden"


class Unauthorized(AppError):
    """Учётные данные отсутствуют, просрочены или не разобраны."""

    code = "unauthorized"
    status = 401
    title = "Unauthorized"


class RateLimited(AppError):
    """Клиент превысил разрешённую частоту обращений."""

    code = "rate-limited"
    status = 429
    title = "Too Many Requests"


class DependencyUnavailable(AppError):
    """Отказала внешняя зависимость: БД, брокер, объектное хранилище."""

    code = "dependency-unavailable"
    status = 503
    title = "Service Unavailable"
