## Шаг 4. Событие

Если ещё не решено, каким механизмом делается побочный эффект (`emit()`,
`after_commit`, задача TaskIQ, консьюмер чужой очереди), — это скилл
`background-effect`; шаги 4, 6 и 7 ниже дают шаблоны под уже принятое решение.

`events.py` — если модуль сообщает о фактах:

```python
"""Доменные события модуля notes."""

from typing import ClassVar
from uuid import UUID

from app.kernel.events.bus import DomainEvent


class NoteCreated(DomainEvent):
    """Заметка создана.

    Событие несёт заголовок, а не только идентификатор: потребитель должен
    уметь обойтись без похода к владельцу таблицы — иначе модули снова
    начинают знать друг о друге.
    """

    topic: ClassVar[str] = "note.created"

    note_id: UUID
    title: str
    owner_id: UUID | None
```

- `topic` обязателен и стабилен: он живёт в очереди дольше выкатки. Формат —
  `<сущность>.<что случилось>` в прошедшем времени;
- событие — факт («заметка создана»), а не команда («отправь письмо»);
- поля события должны быть JSON-сериализуемы: `emit()` вызывает
  `model_dump(mode="json")`;
- на каждую операцию событие заводить не нужно. PATCH и DELETE порождают
  событие только если снаружи на них кто-то реагирует: событие — это контракт,
  который придётся поддерживать.

## Шаг 5. Сервис

`services.py` — единственное место, где вызываются `CRUD` и `emit()`:

```python
"""Бизнес-логика модуля notes."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context import actor_id
from app.kernel.db.crud import CRUD
from app.kernel.events.bus import emit
from app.kernel.pagination import Page, PageParams
from app.modules.notes.events import NoteCreated
from app.modules.notes.models import Note
from app.modules.notes.schemas.requests import NoteCreate, NotePatch


async def create_note(request: NoteCreate, *, session: AsyncSession) -> Note:
    """Создать заметку и сообщить об этом остальному приложению.

    Принимает данные клиента и сессию открытой транзакции, возвращает строку.

    Событие пишется в outbox той же транзакцией: либо есть и заметка, и
    событие, либо нет ни того, ни другого. Транзакцию коммитит зависимость
    `get_uow`, сервис `commit()` не вызывает.
    """
    note = await CRUD.create(Note, request, session, owner_id=actor_id.get())
    emit(session, NoteCreated(note_id=note.id, title=note.title, owner_id=note.owner_id))
    return note


async def get_note(note_id: UUID, *, session: AsyncSession) -> Note:
    """Вернуть заметку по идентификатору.

    Кидает `NotFound`, если строки нет.
    """
    return await CRUD.get_or_404(Note, note_id, session)


async def list_notes(page: PageParams, *, session: AsyncSession) -> Page[Note]:
    """Вернуть страницу заметок по keyset-курсору."""
    return await CRUD.list_page(Note, session, page=page)


async def patch_note(note_id: UUID, patch: NotePatch, *, session: AsyncSession) -> Note:
    """Применить частичное обновление заметки.

    Принимает идентификатор, разобранный патч и сессию открытой транзакции,
    возвращает обновлённую строку. Кидает `NotFound`, если строки нет, и
    `Conflict`, если в патче есть поле вне `Note.__patchable__`.
    """
    note = await CRUD.get_or_404(Note, note_id, session)
    return await CRUD.update(note, patch, session)


async def delete_note(note_id: UUID, *, session: AsyncSession) -> None:
    """Удалить заметку.

    Принимает идентификатор и сессию открытой транзакции, ничего не
    возвращает. Кидает `NotFound`, если строки нет: удалять нечего.
    """
    note = await CRUD.get_or_404(Note, note_id, session)
    await CRUD.delete(note, session)
```

Правила сервиса:

- сессия (или фабрика сессий) приходит **аргументом**, внутри не создаётся;
- `session.commit()` не вызывается никогда — границу держит `get_uow`;
- поднимаются наследники `AppError` (`NotFound`, `Conflict`,
  `ValidationFailed`, `PermissionDenied`), а не `HTTPException`: тот же сервис
  вызывается из воркера и из скрипта;
- `CRUD` умеет `create`, `get`, `get_or_404`, `update`, `delete`, `list_page`.
  Всё сложнее — джойны, агрегаты, батчи — пишется запросом здесь же;
- **внешнего I/O внутри транзакции нет**: ни S3, ни HTTP наружу, ни `kiq()`.
  Если операция сочетает базу и сеть, модуль держит границы сам и порядок
  всегда такой: короткая читающая сессия → закрыли → внешний вызов → короткая
  пишущая транзакция. Образец — `modules/storage/services.py`; вместе с ним
  скопируй сторож `guard_transactions` из `tests/test_storage.py`.

**Физическое удаление против мягкого.** `CRUD.delete` удаляет строку. Если на
неё ссылаются журналы или внешние системы — нужен `SoftDeleteMixin`, и тогда
фильтр `deleted_at IS NULL` пишет сервис: неявного глобального фильтра в
шаблоне нет намеренно. Если у сущности есть содержимое вне БД (объект в
бакете) — удаление двухшаговое, как в `storage`: ручка помечает строку,
периодическая задача убирает объект и только потом строку.

### `emit()` или `after_commit`

| Если эффект… | То | Гарантия |
| --- | --- | --- |
| нельзя потерять (письмо, списание, синхронизация с чужой системой) | `emit(session, Event(...))` | at-least-once: строка в outbox коммитится вместе с данными, публикует релей |
| потерять не жалко (прогрев кеша, метрика, необязательный пинг) | `after_commit(session, fn)` | никаких: процесс, упавший между коммитом и хуком, потеряет его молча |

Ни то, ни другое **не привязано к HTTP-статусу**: триггер — успешный коммит,
решает транзакция, а не ручка. Проверочный вопрос: «а если этот эффект не
случится?» Ответ длиннее одного слова — нужен `emit()`.
