"""Подключение Bearer-аутентификации к помеченным HTTP-ручкам.

Бизнес-модуль ставит чистую метку ``@authenticated`` из ядра. После сборки
приложения этот модуль добавляет зависимость только отмеченным маршрутам:
публичные endpoints не затрагиваются, а политика видна рядом с их кодом.
"""

from collections.abc import Iterable, Iterator
from typing import Final

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.routing import BaseRoute

from app.api.deps import claims_from_headers
from app.kernel.context import actor_id
from app.kernel.errors import Unauthorized
from app.kernel.security.authentication import is_authenticated

#: Тип действующего лица в access JWT. Другие виды субъектов не получают
#: доступ к административной поверхности даже при общей подписи токенов.
ADMIN_KIND: Final = "admin"


async def require_authenticated_admin(request: Request) -> None:
    """Потребовать access JWT администратора и заполнить контекст операции."""
    claims = claims_from_headers(request.headers)
    if claims is None:
        raise Unauthorized(
            "Authentication is required for this operation",
            reason="missing-token",
        )
    if claims.payload.get("kind") != ADMIN_KIND:
        raise Unauthorized("Token is not an admin token", reason="wrong-actor-kind")
    actor_id.set(claims.subject)


def install_authentication(app: FastAPI) -> None:
    """Подключить проверку токена ко всем помеченным маршрутам приложения."""
    for route in _api_routes(app.routes):
        if is_authenticated(route.endpoint):
            _protect(route)


def _api_routes(routes: Iterable[BaseRoute]) -> Iterator[APIRoute]:
    """Перечислить APIRoute, включая endpoints вложенных роутеров."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        included = getattr(route, "original_router", None)
        if isinstance(included, APIRouter):
            yield from _api_routes(included.routes)


def _protect(route: APIRoute) -> None:
    """Добавить маршруту parameterless-зависимость аутентификации один раз."""
    if any(declared.dependency is require_authenticated_admin for declared in route.dependencies):
        return
    route.dependencies.append(Depends(require_authenticated_admin))
