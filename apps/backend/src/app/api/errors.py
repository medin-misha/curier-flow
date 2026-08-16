"""Перевод исключений в ответы RFC 9457 problem+json.

Единственная точка, где прикладная ошибка превращается в HTTP-ответ. Формат
один для всех источников: доменной ошибки, ошибки разбора запроса FastAPI,
ответа самого фреймворка (404 на неизвестный путь, 405 на неверный метод) и
необработанного исключения. Голый `{"detail": "..."}` наружу не уходит
никогда — клиент разбирает ошибки по одной схеме.
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Final, cast

import structlog
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException  # noqa: TID251  # см. install_error_handlers
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ExceptionHandler

from app.api.middleware import REQUEST_ID_HEADER
from app.kernel.config import settings
from app.kernel.context import request_id
from app.kernel.errors import (
    AppError,
    Conflict,
    DependencyUnavailable,
    NotFound,
    PermissionDenied,
    RateLimited,
    Unauthorized,
    ValidationFailed,
)

PROBLEM_CONTENT_TYPE: Final = "application/problem+json"

#: Стандартные члены problem+json. Дополнительные поля ошибки не вправе их
#: перезаписать: клиент разбирает ответ по этим ключам, и подменённый `status`
#: или `type` — это уже другой ответ, а не уточнение к нему.
_RESERVED_MEMBERS: Final = frozenset(
    {"type", "title", "status", "detail", "instance", "request_id"}
)

#: Статусы, у которых есть прикладной аналог в ядре. Нужны, чтобы 404 от
#: маршрутизатора и 404 из сервиса выглядели для клиента одинаково: один
#: `type`, один `title`, различие только в `detail`.
_KERNEL_ERRORS: Final[Mapping[int, type[AppError]]] = {
    error.status: error
    for error in (
        Unauthorized,
        PermissionDenied,
        NotFound,
        Conflict,
        ValidationFailed,
        RateLimited,
        DependencyUnavailable,
    )
}

_logger = structlog.get_logger("app.api.errors")


def install_error_handlers(app: FastAPI) -> None:
    """Подключить обработчики ошибок к приложению.

    `cast` неизбежен: Starlette типизирует обработчик как принимающий любой
    `Exception`, а сужение по классу гарантирует сама регистрация — до
    обработчика доходит только тот тип, на который он зарегистрирован.
    """
    app.add_exception_handler(AppError, cast(ExceptionHandler, handle_app_error))
    app.add_exception_handler(
        RequestValidationError, cast(ExceptionHandler, handle_validation_error)
    )
    # HTTPException в коде приложения запрещён линтером, но его поднимает сам
    # фреймворк: неизвестный путь, неверный метод, слишком большое тело.
    app.add_exception_handler(HTTPException, cast(ExceptionHandler, handle_http_exception))
    app.add_exception_handler(Exception, handle_unexpected_error)


async def handle_app_error(request: Request, exc: AppError) -> Response:
    """Доменная ошибка: статус, код и заголовок берутся из класса ошибки."""
    return _problem(
        request,
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        extra=exc.extra,
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
    """Ошибка разбора запроса FastAPI, приведённая к общему формату.

    Наружу отдаются только место, сообщение и тип нарушения. `input` и `url`,
    которые кладёт в отчёт pydantic, отбрасываются: первое возвращает клиенту
    его же данные (в том числе пароли), второе ссылается на документацию
    pydantic, а не на наш API.
    """
    violations = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return _problem(
        request,
        status=ValidationFailed.status,
        code=ValidationFailed.code,
        title=ValidationFailed.title,
        detail="Request validation failed",
        extra={"errors": violations},
    )


async def handle_http_exception(request: Request, exc: HTTPException) -> Response:
    """Ответ самого фреймворка: 404 на неизвестный путь, 405 на метод и прочие."""
    code, title = _describe(exc.status_code)
    return _problem(
        request,
        status=exc.status_code,
        code=code,
        title=title,
        detail=str(exc.detail) if exc.detail else title,
        # Заголовки фреймворка несут смысл ответа: `Allow` в 405 и
        # `WWW-Authenticate` в 401 без них теряются.
        headers=exc.headers,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Необработанное исключение: подробности в лог, наружу — пустой 500.

    Наружу не уходит ни тип исключения, ни сообщение: и то и другое выдаёт
    устройство сервиса, а клиенту не поможет. Связать ответ с трейсбеком можно
    по `request_id`, он есть и в теле, и в записи лога.
    """
    # exc_info передаётся объектом, а не флагом: обработчик вызывается из
    # ServerErrorMiddleware, и полагаться на текущий sys.exc_info() здесь
    # значит зависеть от того, как именно нас позвали.
    _logger.error(
        "http.unhandled_error",
        path=request.url.path,
        error=type(exc).__name__,
        exc_info=exc,
    )
    return _problem(
        request,
        status=AppError.status,
        code=AppError.code,
        title=AppError.title,
        detail="Internal server error",
    )


def _describe(status: int) -> tuple[str, str]:
    """Подобрать код и заголовок проблемы по HTTP-статусу."""
    kernel_error = _KERNEL_ERRORS.get(status)
    if kernel_error is not None:
        return kernel_error.code, kernel_error.title
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        return "http-error", "HTTP Error"
    return phrase.lower().replace(" ", "-"), phrase


def _problem(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    extra: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Собрать ответ problem+json.

    `X-Request-ID` ставится здесь, а не только в middleware: ответ 500
    формирует ServerErrorMiddleware, который находится снаружи цепочки
    middleware, и его ответ мимо неё и уходит.
    """
    current_id = request_id.get()
    body: dict[str, Any] = {
        "type": f"{settings.errors_base_url.rstrip('/')}/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": current_id,
    }
    if extra:
        # jsonable_encoder: в extra прилетают UUID и datetime из доменного
        # кода, а падение сериализации ответа об ошибке превратило бы понятный
        # 409 в невнятный 500.
        body.update(
            jsonable_encoder(
                {key: value for key, value in extra.items() if key not in _RESERVED_MEMBERS}
            )
        )

    response_headers = {REQUEST_ID_HEADER: current_id}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        body,
        status_code=status,
        headers=response_headers,
        media_type=PROBLEM_CONTENT_TYPE,
    )
