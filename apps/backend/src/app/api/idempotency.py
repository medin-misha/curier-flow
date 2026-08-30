"""Подключение `Idempotency-Key` к ручкам, помеченным `@idempotent`.

Что здесь происходит на одном запросе:

1. для `@authenticated` сначала проверить Admin access JWT, чтобы replay не
   обходил защиту ручки;
2. до остальных зависимостей — прочитать ключ, посчитать отпечаток запроса,
   поискать сохранённый ответ и, если он есть, вернуть его, не выполняя ручку;
3. в транзакции запроса — занять ключ (`INSERT ... ON CONFLICT DO NOTHING`);
4. после ручки, но всё ещё до коммита — записать ответ в ту же транзакцию.

Отсюда главное свойство: ключ, данные и сохранённый ответ уезжают в базу одним
коммитом. Упавший запрос откатывает все три вещи сразу, поэтому «ключ занят, а
данных нет» не бывает и застрявших ключей после падения процесса не остаётся.

Почему не middleware
--------------------
Middleware выполняется на каждом запросе, включая те, к которым правило не
относится. Идемпотентность обязана включаться осознанно на конкретной ручке:
GET и DELETE в ней не нуждаются, а неявная запись ответов всех ручек в таблицу
— это сюрприз, который находят по распухшей базе. Кроме того, middleware
работает снаружи транзакции запроса и физически не может положить ключ в неё.

Почему сборка, а не класс маршрута в модуле
-------------------------------------------
Стандартный способ обернуть обработчик — свой класс `APIRoute`, переданный
в `APIRouter(route_class=...)`. Модулю он недоступен: класс живёт в слое `api`,
а правило `api → modules` запрещает модулю импортировать `api`. Поэтому модуль
ставит метку `@idempotent` из ядра (тот же приём, что `@subscribe` и
`@schedule`), а класс маршрута подставляет сборка приложения — здесь. Заодно
правило «идемпотентность подключена» становится проверяемым в одном месте, а не
рассыпанным по роутерам модулей.
"""

from collections.abc import Callable, Coroutine, Iterable, Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Final, cast

from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute

from app.api.authentication import require_authenticated_admin
from app.api.deps import Uow, actor_from_headers
from app.api.middleware import REQUEST_ID_HEADER
from app.kernel.db import session as db_session
from app.kernel.errors import Conflict, ValidationFailed
from app.kernel.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    MAX_KEY_LENGTH,
    IdempotencyStatus,
    find_key,
    is_idempotent,
    release_key,
    request_digest,
    reserve_key,
    store_response,
)
from app.kernel.security.authentication import is_authenticated

#: Признак того, что ответ не выполнен заново, а взят из-под ключа. Клиенту он
#: нужен редко, а вот при разборе «почему счёт не создался» отвечает на главный
#: вопрос сразу.
REPLAY_HEADER: Final = "Idempotency-Replayed"

#: Ключ в `request.state`, под которым обработчик маршрута и зависимость
#: передают друг другу бронь ключа.
STATE_ATTR: Final = "idempotency"

#: Заголовки, которые принадлежат конкретной передаче, а не ответу. Сохранять
#: их нельзя: `content-length` пересчитает сервер, `date` соврёт о времени, а
#: чужой `x-request-id` увёл бы разбор инцидента в логи прошлого запроса.
_VOLATILE_HEADERS: Final = frozenset(
    {
        "content-length",
        "date",
        "server",
        "connection",
        "keep-alive",
        "transfer-encoding",
        REQUEST_ID_HEADER,
    }
)

#: Обработчик маршрута FastAPI: принимает запрос, возвращает готовый ответ.
RouteHandler = Callable[[Request], Coroutine[Any, Any, Response]]


@dataclass(slots=True)
class _Reservation:
    """Бронь ключа на время запроса.

    `session` заполняет зависимость: транзакция запроса появляется позже, чем
    обработчик маршрута считает ключ, а записать ответ нужно именно в неё.
    """

    key: str
    request_hash: str
    session: AsyncSession | None = None


class IdempotentRoute(APIRoute):
    """Маршрут, который отвечает копией ответа на повтор с тем же ключом.

    Единственная точка расширения FastAPI, из которой виден и запрос, и
    готовый ответ. Обёртка исполняется внутри стека зависимостей, поэтому
    транзакция запроса на этот момент ещё открыта — именно в неё и уходит
    сохранённый ответ.

    Это верно и с `scope="function"` у транзакции: FastAPI закрывает такие
    зависимости после того, как обработчик маршрута вернул ответ, а обёртка —
    часть этого обработчика. То есть ответ дописывается в ту же транзакцию, и
    только потом она коммитится — до отправки ответа клиенту.
    """

    def get_route_handler(self) -> RouteHandler:
        """Обернуть штатный обработчик проверкой ключа и сохранением ответа."""
        return _guarded(
            super().get_route_handler(),
            requires_authentication=is_authenticated(self.endpoint),
        )


def install_idempotency(app: FastAPI) -> None:
    """Подключить `Idempotency-Key` ко всем помеченным ручкам приложения.

    Принимает собранное приложение, ничего не возвращает. Вызывается после
    подключения роутеров: до этого маршрутов в приложении ещё нет.

    Повторный вызов на тех же маршрутах ничего не меняет, и это важно:
    `include_router` маршруты не копирует, а приложение из одного и того же
    реестра собирают за процесс не раз — как минимум в тестах.
    """
    for route in _api_routes(app.routes):
        if is_idempotent(route.endpoint):
            _protect(route)


async def reserve_idempotency_key(
    request: Request,
    uow: Uow,
    key: Annotated[str, Header(alias=IDEMPOTENCY_KEY_HEADER)],
) -> None:
    """Занять ключ идемпотентности в транзакции запроса.

    Кидает `Conflict`, если ключ уже занят другим запросом.

    Зависимость, а не код обработчика маршрута: транзакция запроса существует
    только внутри дерева зависимостей, а ключ обязан лежать в ней. Объявлена
    первой, поэтому параллельный дубликат отсеивается до того, как ручка
    начнёт работу.
    """
    reservation = cast(_Reservation, getattr(request.state, STATE_ATTR))
    if not await reserve_key(uow, key=key, request_hash=reservation.request_hash):
        raise Conflict(
            "A request with this Idempotency-Key is still in flight",
            reason="in-flight",
        )
    reservation.session = uow


def _api_routes(routes: Iterable[BaseRoute]) -> Iterator[APIRoute]:
    """Перечислить ручки приложения, спускаясь во включённые роутеры.

    `include_router` не копирует маршруты, а кладёт в список ссылку на
    включённый роутер: объекты ручек остаются теми же, что объявил модуль.
    Признак такой ссылки — атрибут `original_router`; проверяется он утиной
    типизацией, потому что сам класс ссылки в FastAPI непубличный.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        included = getattr(route, "original_router", None)
        if isinstance(included, APIRouter):
            yield from _api_routes(included.routes)


def _protect(route: APIRoute) -> None:
    """Подключить маршруту занятие ключа и сохранение ответа.

    Правки две, и обе — над готовым маршрутом, потому что раньше его не
    существует:

    * зависимость дописывается в `route.dependencies`, то есть в тот же
      публичный список, из которого FastAPI собирает дерево зависимостей
      ручки на каждый запрос;
    * класс маршрута подменяется на `IdempotentRoute`. Подмена `__class__`
      здесь безопасна: наследник не добавляет ни одного поля и отличается
      единственным переопределённым методом, а обработчик FastAPI строит
      вызовом `self.get_route_handler()` — то есть уже через новый класс.
      Полноценная передача `route_class` невозможна: роутер создаёт модуль, а
      импортировать `api` ему нельзя.
    """
    if any(declared.dependency is reserve_idempotency_key for declared in route.dependencies):
        return

    route.dependencies.append(Depends(reserve_idempotency_key))
    route.__class__ = IdempotentRoute


def _guarded(handler: RouteHandler, *, requires_authentication: bool) -> RouteHandler:
    """Обернуть маршрут auth-проверкой, ключом и сохранением ответа."""

    async def guarded(request: Request) -> Response:
        # Replay не должен обходить marker-зависимость, которая живёт внутри
        # штатного FastAPI handler и иначе выполнилась бы слишком поздно.
        if requires_authentication:
            await require_authenticated_admin(request)
        key = _required_key(request.headers)
        digest = request_digest(
            method=request.method,
            path=request.url.path,
            actor_id=actor_from_headers(request.headers),
            # Тело уже прочитано и закешировано Starlette к моменту, когда
            # FastAPI начнёт разбирать его в схему, поэтому чтение здесь
            # ничего у ручки не отбирает.
            body=await request.body(),
        )

        replayed = await _replay(key, digest)
        if replayed is not None:
            return replayed

        setattr(request.state, STATE_ATTR, _Reservation(key=key, request_hash=digest))
        response = await handler(request)
        await _remember(request, response)
        return response

    return guarded


def _required_key(headers: Headers) -> str:
    """Прочитать заголовок ключа.

    Кидает `ValidationFailed`, если ключа нет или он длиннее предела.

    Ключ обязателен: ручка помечена `@idempotent`, то есть обещает защиту от
    повтора, а запрос без ключа получить её не может. Промолчать здесь значит
    отдать клиенту незаметно ослабленную гарантию.
    """
    key = headers.get(IDEMPOTENCY_KEY_HEADER)
    if not key:
        raise ValidationFailed(
            f"{IDEMPOTENCY_KEY_HEADER} header is required for this operation",
            header=IDEMPOTENCY_KEY_HEADER,
        )
    if len(key) > MAX_KEY_LENGTH:
        raise ValidationFailed(
            f"{IDEMPOTENCY_KEY_HEADER} must be at most {MAX_KEY_LENGTH} characters",
            header=IDEMPOTENCY_KEY_HEADER,
        )
    return key


async def _replay(key: str, digest: str) -> Response | None:
    """Вернуть сохранённый под ключом ответ, если он есть.

    Кидает `Conflict`, если ключ занят другим запросом или ответ под ним
    невоспроизводим.

    Читается отдельной короткой сессией: транзакции запроса на этот момент ещё
    нет — она откроется зависимостью, когда станет ясно, что работу всё-таки
    надо выполнить.
    """
    async with db_session.session_factory() as session:
        stored = await find_key(session, key)

    if stored is None:
        return None

    if stored.request_hash != digest:
        raise Conflict(
            f"{IDEMPOTENCY_KEY_HEADER} was already used for a different request",
            reason="payload-mismatch",
        )

    if stored.status is not IdempotencyStatus.COMPLETED or stored.response_status is None:
        raise Conflict(
            "The response for this Idempotency-Key cannot be replayed",
            reason="in-progress",
        )

    headers = dict(stored.response_headers or {})
    headers[REPLAY_HEADER] = "true"
    return Response(
        content=stored.response_body,
        status_code=stored.response_status,
        headers=headers,
    )


async def _remember(request: Request, response: Response) -> None:
    """Сохранить ответ под ключом или освободить ключ.

    Записывает в ту же транзакцию, в которой ключ занят: коммит зависимости
    ещё не случился, поэтому данные, ключ и ответ станут видны одновременно.

    Неуспешный ответ ключ освобождает. Ошибка означает, что операция не
    состоялась (транзакция с исключением и вовсе откатывается целиком), и
    защищать от повтора нечего — а вот запретить клиенту повторить запрос тем
    же ключом после сбоя было бы вредно: именно для этого случая ключ и нужен.
    """
    reservation = cast(_Reservation, getattr(request.state, STATE_ATTR))
    if reservation.session is None:
        # До зависимости дело не дошло — значит и ключ не занят.
        return

    if response.status_code >= 400:  # noqa: PLR2004  # 4xx и 5xx, граница из RFC 9110
        await release_key(reservation.session, key=reservation.key)
        return

    body = getattr(response, "body", None)
    if body is None:
        # Потоковый ответ: тела ещё нет и повторить его нечем. Строка остаётся
        # `in_progress`, и повтор получит 409 вместо пустого тела.
        return

    await store_response(
        reservation.session,
        key=reservation.key,
        status=response.status_code,
        body=body,
        headers=_storable(response.headers),
    )


def _storable(headers: Headers) -> dict[str, str]:
    """Оставить только те заголовки ответа, которые переживают повтор."""
    return {name: value for name, value in headers.items() if name not in _VOLATILE_HEADERS}
