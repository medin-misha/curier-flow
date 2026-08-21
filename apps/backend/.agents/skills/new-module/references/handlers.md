## Шаг 8. Ручки

`handlers.py` — только HTTP:

```python
"""HTTP-ручки модуля notes."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.pagination import Page, PageParams
from app.modules.notes.schemas.requests import NoteCreate, NotePatch
from app.modules.notes.schemas.responses import NoteResponse
from app.modules.notes.services import (
    create_note,
    delete_note,
    get_note,
    list_notes,
    patch_note,
)

#: Псевдонимы объявлены здесь, а не взяты из `app.api.deps`: правило слоёв
#: `api → modules → platform → kernel` запрещает модулю импортировать api.
#:
#: `scope="function"` — не украшение, а инвариант «коммит → ответ». С областью
#: по умолчанию FastAPI закрывает зависимость уже после отправки ответа, и
#: упавший коммит достаётся клиенту как 2xx. Проверяет это
#: `tests/test_architecture.py::test_uow_dependencies_close_before_the_response`.
Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
PageQuery = Annotated[PageParams, Depends()]

router = APIRouter(tags=["notes"])


@router.post("", status_code=HTTPStatus.CREATED, summary="Create a note")
async def create(body: NoteCreate, uow: Uow) -> NoteResponse:
    """Создать заметку."""
    return NoteResponse.model_validate(await create_note(body, session=uow))


@router.get("", summary="List notes")
async def list_page(page: PageQuery, session: RoSession) -> Page[NoteResponse]:
    """Отдать страницу заметок по keyset-курсору."""
    found = await list_notes(page, session=session)
    return Page[NoteResponse](
        items=[NoteResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/{note_id}", summary="Note by id")
async def retrieve(note_id: UUID, session: RoSession) -> NoteResponse:
    """Отдать одну заметку."""
    return NoteResponse.model_validate(await get_note(note_id, session=session))


@router.patch("/{note_id}", summary="Update a note")
async def update(note_id: UUID, body: NotePatch, uow: Uow) -> NoteResponse:
    """Изменить поля заметки, перечисленные в теле запроса."""
    return NoteResponse.model_validate(await patch_note(note_id, body, session=uow))


@router.delete("/{note_id}", status_code=HTTPStatus.NO_CONTENT, summary="Delete a note")
async def remove(note_id: UUID, uow: Uow) -> None:
    """Удалить заметку; повторный вызов отвечает 404."""
    await delete_note(note_id, session=uow)
```

Правила ручки:

- **не импортирует `CRUD`** и вообще ничего из `app.kernel.db.crud`;
- **не вызывает `session.commit()`**;
- не ходит в S3, брокер и по HTTP наружу;
- не содержит бизнес-правил: разобрал запрос, позвал сервис, собрал ответ;
- пишущей ручке (`POST`, `PATCH`, `DELETE`) — `Uow`, читающей — `RoSession`;
- путь `""` — это корень префикса модуля (`/notes`), `"/{id}"` — элемент;
- `PUT`-ручек в шаблоне нет ни одной: полная замена ресурса потребовала бы от
  клиента прислать и те поля, которые определяет сервер. Изменение — `PATCH`.

**DELETE отвечает 204 и `-> None`.** `status_code=HTTPStatus.NO_CONTENT` плюс
возврат `None`: тело у 204 запрещено, схема ответа такой ручке не нужна (это и
есть строка «`schemas/responses.py` не создаётся, если ручки отвечают только
204» из таблицы шага 1).

**Повторный DELETE — 404.** Сервис идёт через `CRUD.get_or_404`, и второй вызов
строки не находит. Так же ведёт себя `storage`: пока строка есть,
`DELETE /files/{id}` отвечает 204 сколько угодно раз, а после того как её убрала
задача — 404, и `GET` на неё отвечает 404 с того же момента. Идемпотентность
DELETE — про эффект, а не про статус: после любого числа вызовов ресурса нет.
Отдавать 204 на неизвестный id значит отдавать его и на опечатку в адресе, то
есть прятать ошибку клиента.

Обратное решение (всегда 204) оправдано, когда клиент повторяет DELETE вслепую
по таймауту и считает 404 отказом. Тогда сервис молчит на отсутствующей строке —
но это осознанное решение модуля, и его место в его `AGENTS.md`.

Идемпотентность записи, если повтор запроса не должен создавать вторую
сущность:

```python
from app.kernel.idempotency import idempotent

@router.post("", status_code=HTTPStatus.CREATED)
@idempotent
async def create(body: NoteCreate, uow: Uow) -> NoteResponse:
    ...
```

Метку ставят **только на создающие ручки** и осознанно: помеченная ручка
требует заголовок `Idempotency-Key` и без него отвечает 422. `GET`, `DELETE` и
`PATCH`, присваивающий присланные значения, в ней не нуждаются: повтор ничего
не создаёт и приводит к тому же состоянию.
