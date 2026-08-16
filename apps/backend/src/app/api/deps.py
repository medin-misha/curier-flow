"""Общие зависимости HTTP-слоя.

Типизированные псевдонимы, а не голый `Depends` в каждой сигнатуре: граница
транзакции и требование авторизации — решения архитектуры, и они должны быть
видны в сигнатуре ручки одним словом. Заодно это не даёт хендлеру взять сессию
мимо зависимости.

Бизнес-модулю эти псевдонимы недоступны: правило слоёв
`api → modules → platform → kernel` запрещает ему импортировать `api`, поэтому
модуль объявляет свои — из тех же функций ядра. Дублирование одной строки здесь
дешевле, чем зависимость модуля от веб-слоя.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.requests import Request

from app.kernel.context import actor_id
from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.errors import Unauthorized
from app.kernel.pagination import PageParams
from app.kernel.security.tokens import TokenType, decode_token, jwt_settings

#: Пишущая транзакция на запрос: коммит при штатном выходе, откат при ошибке.
#: Хендлер `commit()` не вызывает — иначе одна операция распадается на
#: несколько, и откат перестаёт откатывать.
#:
#: `scope="function"` здесь — не украшение, а сам инвариант «коммит → ответ».
#: По умолчанию FastAPI закрывает зависимость с `yield` после того, как ответ
#: уже ушёл клиенту: упавший коммит (нарушенное отложенное ограничение,
#: дедлок, обрыв соединения с базой) достался бы клиенту как 2xx, а исключение
#: возникло бы позже и осталось бы только в логе. С `function` зависимость
#: закрывается сразу после того, как обработчик маршрута вернул готовый ответ,
#: и до его отправки: упавший коммит превращается в обычное исключение, а его
#: обрабатывает `app.api.errors` — 500 в формате problem+json.
Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]

#: Сессия только для чтения: транзакция не открывается, коммитить нечего.
#: Область оставлена стандартной: коммита у неё нет, ломаться при закрытии
#: нечему, а сессия, живущая до конца отправки ответа, позволяет отдавать
#: ответ потоком, дочитывая курсор по мере передачи.
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]

#: Параметры страницы из query-строки: `?cursor=...&limit=...`.
PageQuery = Annotated[PageParams, Depends()]


def actor_from_headers(headers: Headers) -> UUID | None:
    """Достать действующее лицо из заголовка `Authorization`.

    Принимает заголовки запроса, возвращает идентификатор пользователя или
    `None`, если заголовка нет. Кидает `Unauthorized`, если заголовок есть, но
    негоден: не та схема, испорченная подпись, истёкший срок, refresh вместо
    access.

    Отсутствие заголовка — это `None`, а не ошибка: модуля авторизации в
    шаблоне нет, и требование токена на каждой ручке сделало бы шаблон
    незапускаемым. А вот присланный негодный токен молчаливым `None` быть не
    может: клиент считает себя авторизованным, и «тихо стал анонимом» — это
    вместо понятного 401 непонятный 404 где-то в бизнес-логике.

    Обычная функция, а не зависимость: тот же разбор нужен обработчику
    маршрута с `Idempotency-Key` — он считает отпечаток запроса до того, как
    FastAPI дойдёт до зависимостей.
    """
    authorization = headers.get("authorization")
    if authorization is None:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Authorization header must use the Bearer scheme", reason="bad-scheme")

    return decode_token(token, expected=TokenType.ACCESS, settings=jwt_settings).subject


async def get_actor(request: Request) -> UUID | None:
    """Опознать действующее лицо и положить его в контекст операции.

    Возвращает идентификатор пользователя или `None` для анонимного вызова.
    Кидает `Unauthorized` на негодный токен.

    Contextvar заполняется здесь, потому что HTTP-зависимость — это транспорт,
    а `actor_id` нужен коду, до которого его не дотащить аргументами: логам,
    `emit()` (он кладёт актора в заголовки доменного события) и владельцу
    строки в `CRUD.create`. Ручка, не объявившая эту зависимость, оставляет
    контекст пустым — и это честно: она не проверяла, кто пришёл.
    """
    actor = actor_from_headers(request.headers)
    actor_id.set(actor)
    return actor


#: Необязательный актор: `None`, если запрос анонимный.
Actor = Annotated[UUID | None, Depends(get_actor)]


async def require_actor(actor: Actor) -> UUID:
    """Потребовать опознанного пользователя.

    Возвращает его идентификатор. Кидает `Unauthorized`, если токена не было.
    """
    if actor is None:
        raise Unauthorized("Authentication is required for this operation", reason="missing-token")
    return actor


#: Обязательный актор: одна строка в сигнатуре ручки вместо проверки в теле.
CurrentActor = Annotated[UUID, Depends(require_actor)]
