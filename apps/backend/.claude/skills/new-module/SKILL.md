---
name: new-module
description: Создать новый бизнес-модуль в этом шаблоне — каталог src/app/modules/<name>/ с handlers, services, models, schemas, манифестом, миграцией, тестами и .claude/CLAUDE.md, плюс регистрация в MODULES. Применяй, когда просят «добавь модуль», «сделай ресурс/сущность», «новые ручки для X», «CRUD для X», «add a module», «new endpoint for X» в этом репозитории. Не применяй для правки уже существующего модуля — там читай его собственный .claude/CLAUDE.md.
---

# Создание бизнес-модуля

Модуль — единица поставки в этом шаблоне. Правильно созданный модуль требует
правок **только внутри своего каталога плюс регистрации в `MODULES`** (две
строки в `src/app/modules/__init__.py`: импорт манифеста и его имя в кортеже).
Если по ходу работы захотелось поправить `kernel/config.py`, `alembic/env.py`,
`api/router.py` или `main.py` — это признак того, что что-то делается не тем
способом; вернись к шагам ниже.

Перед началом прочитай правила, которые касаются модуля целиком:
`.claude/rules/module-layout.md` (состав файлов и слои),
`.claude/rules/transactions.md` (границы транзакции и коммит раньше ответа),
`.claude/rules/events.md` (события и подписчики). Они подтягиваются сами при
чтении готовых файлов, но модуля, который ты создаёшь, ещё нет — поэтому
прочитай их явно. Здесь только порядок действий и шаблоны.

## Шаг 0. Выясни, что именно нужно

Не начинай писать файлы, пока не знаешь ответы:

1. **Имя модуля** (`orders`, `notes`, `billing`) и имя ресурса в URL. Модуль
   называется по своей роли, ресурс — по тому, чем управляет: модуль `storage`
   вешает ручки на `/files`.
2. **Поля сущности**: какие приходят от клиента, какие определяет сервер
   (владелец, статус, ключ, отметки времени).
3. **Операции**: создание, чтение по id, список, частичное изменение,
   удаление. Не создавай ручки «на будущее» — только те, что нужны.
4. **Что клиент вправе менять после создания** — это будущий `__patchable__`.
5. **События**: о каком факте модуль обязан сообщить остальному приложению.
6. **Подписки**: на чьи **чужие** события он реагирует.
7. **Фоновая работа**: периодические задачи, обмен с внешними сервисами.
8. **Настройки**: лимиты, TTL, расписания.

Если чего-то из этого нет — соответствующего файла тоже не будет (шаг 1).

## Шаг 1. Реши состав файлов

**Файл создаётся только если ему есть что содержать.** Пустая заглушка
выглядит как незаконченная работа и провоцирует дописать логику туда, где её не
должно быть. Образец — модуль `health`: в нём нет ни `models/`, ни
`schemas/requests.py`, ни `subscribers.py`, и в его `.claude/CLAUDE.md`
написано, почему.

| Файл | Создаётся | Не создаётся, если |
| --- | --- | --- |
| `__init__.py` | всегда (докстринг в одну строку) | — |
| `handlers.py` | если у модуля есть HTTP-ручки | модуль только слушает события или крутит задачи |
| `services.py` | почти всегда | логики нет вовсе |
| `models/__init__.py` + `models/<entity>.py` | если модуль владеет таблицами | своих таблиц нет |
| `schemas/__init__.py` | вместе с любым файлом в `schemas/` (докстринг в одну строку) | схем нет вовсе |
| `schemas/requests.py` | если хоть одна ручка принимает тело или параметры | ручки только читают по пути |
| `schemas/responses.py` | если ручки что-то отдают | ручки отвечают только 204 |
| `events.py` | если модуль порождает доменные события | не порождает |
| `subscribers.py` | если модуль слушает **чужие** события (шаг 6) | не слушает |
| `tasks.py` | если есть периодические или отложенные задачи | нет фоновой работы |
| `consumers.py` | если модуль читает очередь внешнего сервиса | не читает |
| `module.py` | всегда | — |
| `.claude/CLAUDE.md` | всегда | — |
| `tests/test_<name>.py` | всегда | — |

`models/` — именно **пакет**, а не файл: Alembic импортирует его по имени из
манифеста (`Module.models`), и таблицы обязаны попасть в метаданные от этого
импорта.

## Шаг 2. Модель

`src/app/modules/<name>/models/<entity>.py`:

```python
"""Таблица `notes`: заметка пользователя."""

from uuid import UUID

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class Note(UUIDPkMixin, TimestampMixin, Base):
    """Заметка: заголовок, текст и владелец."""

    __tablename__ = "notes"

    #: Белый список полей для PATCH. Пустой по умолчанию: разрешение выдаётся
    #: явно, а не забывается. `status`, `owner_id` и всё, что определяет
    #: сервер, сюда попадать не должно.
    __patchable__ = frozenset({"title", "body"})

    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)

    #: Владелец из `actor_id`. Nullable, пока в шаблоне нет аутентификации.
    owner_id: Mapped[UUID | None] = mapped_column(default=None)


#: Индекс под keyset-пагинацию: порядок колонок и направление обязаны совпадать
#: с `ORDER BY created_at DESC, id DESC` в `CRUD.list_page`, иначе Postgres
#: досортировывает выборку. Объявлен после класса, а не в `__table_args__`:
#: внутри тела класса колонок ещё нет, а строка вместо выражения потеряла бы
#: направление сортировки.
Index("ix_notes_keyset", Note.created_at.desc(), Note.id.desc())
```

Обязательное:

- **`Index("ix_<table>_keyset", Model.created_at.desc(), Model.id.desc())`
  после класса — у каждой таблицы, которую будут листать.** Без него
  keyset-пагинация вырождается в сортировку всей таблицы. Это правило не
  проверяется автоматически: узнать из схемы, листают ли таблицу, нельзя.
- `__patchable__` — даже если PATCH-ручки нет. Пустой `frozenset()` означает,
  что случайно добавленный позже PATCH не пропустит ни одного поля, пока
  разрешение не выдадут явно.
- Индексы под запросы задач и фильтров — в `__table_args__` (там ссылки на
  колонки идут строками, направление сортировки не нужно).
- Уникальные ограничения там, где дубль означает потерю данных.
- Enum-колонка — `Enum(..., native_enum=False, values_callable=...)`: новое
  состояние не должно требовать `ALTER TYPE`. Образец со всеми аргументами —
  `modules/storage/models/file.py`.

`models/__init__.py`:

```python
"""Модели модуля notes.

Пакет, а не один файл: alembic импортирует его по имени из манифеста
(`Module.models`), и таблицы обязаны попасть в метаданные от этого импорта.
"""

from app.modules.notes.models.note import Note

__all__ = ["Note"]
```

## Шаг 3. Схемы

### Схема создания

`schemas/requests.py` — то, что вправе прислать клиент:

```python
"""Схемы запросов модуля notes.

В схемах нет ни `owner_id`, ни `status`, ни служебных отметок: всё это
определяет сервер и передаёт в `CRUD.create` через `**overrides`.
"""

from pydantic import Field

from app.kernel.schemas import BaseRequest


class NoteCreate(BaseRequest):
    """Новая заметка."""

    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
```

**Что попадает в схему запроса, а что нет.** Правило одно: в схему попадает
только то, что клиент имеет право задать. Всё остальное — владелец
(`actor_id`), начальный статус, сгенерированный сервером ключ, отметки времени,
ETag, идентификатор — передаётся отдельно:

```python
note = await CRUD.create(Note, request, session, owner_id=actor_id.get())
```

`CRUD.create` берёт `dto.model_dump()` и накрывает его `**overrides`, поэтому
одноимённое поле схемы будет перекрыто. Но полагаться на это нельзя: поле,
оставленное в схеме, попадает в OpenAPI, и клиент разумно решит, что его можно
задать. `BaseRequest` объявлен с `extra="forbid"`, так что лишнее поле в теле
вернёт 422 — этим и надо пользоваться.

### Схема частичного обновления (PATCH)

Отличие PATCH от POST одно: у поля три состояния — «прислано со значением»,
«не прислано» и «прислано как `null`». Первые два различает `CRUD.update` сам
(он берёт `model_dump(exclude_unset=True)`, иначе PATCH затирал бы дефолтами
всё, чего в запросе не было). Третье обязана различать схема — в тот же
`requests.py`, добавив к импортам `from typing import Self` и
`from pydantic import model_validator`:

```python
class NotePatch(BaseRequest):
    """Частичное обновление заметки.

    Поля необязательны, но `null` не значение: пропущенное поле означает «не
    трогай», а явный `null` — попытку записать NULL в NOT NULL-колонку.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _forbid_explicit_nulls(self) -> Self:
        """Отвергнуть поля, присланные клиентом со значением `null`."""
        nulled = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulled:
            raise ValueError(f"Fields must not be null: {', '.join(nulled)}")
        return self
```

Почему именно так, а не двумя более короткими способами:

| Запись | Что получится |
| --- | --- |
| `title: str \| None = None`, валидатора нет | `{"title": null}` доезжает до NOT NULL-колонки: опечатка клиента становится 500 |
| `title: str = Field(default=None)` | `make check` красный: плагин pydantic для mypy выдаёт `Incompatible types in assignment (expression has type "None", variable has type "str")` |
| запись выше | `{}` → ничего не меняем, `{"title": "x"}` → меняем одно поле, `{"title": null}` → 422 |

Детали, на которые уходит время, если не знать:

- различить «прислали `null`» и «не прислали ничего» можно **только** через
  `model_fields_set`: в обоих случаях в атрибуте лежит один и тот же `None`;
- `-> Self` обязателен: mypy строг ко всем сигнатурам, а валидатор `mode="after"`
  возвращает саму модель;
- `ValueError` внутри валидатора FastAPI превращает в 422 problem+json
  (`{"loc": ["body"], "msg": "Value error, Fields must not be null: title"}`);
- валидатор не нужен, если **все** патчируемые колонки nullable: там `null` —
  законный способ очистить поле. Появилась среди них NOT NULL — валидатор
  обязателен;
- пустое тело `{}` — законный запрос: изменений нет, ответ 200 и та же строка
  (SQLAlchemy не отправит UPDATE, `updated_at` не сдвинется). Требование «хотя
  бы одно поле» ставится тем же валидатором, если оно нужно.

**Два рубежа защиты, и они разные.** Схема отвечает за то, что клиент вправе
*прислать*: `extra="forbid"` даёт 422 на поле, которого в `NotePatch` нет.
`Model.__patchable__` отвечает за то, что вправе измениться в *строке*:
`CRUD.update` даёт `Conflict` (409) на поле, которое в схему попало, а в белый
список — нет (не тихая фильтрация: клиент, попросивший сменить `status`, должен
узнать, что этого не произошло). Пока списки совпадают, 409 по HTTP не
случится — он сторожит момент, когда поле добавили в схему и забыли в
`__patchable__`, и вызовы сервиса не из ручки.

### Схема ответа

`schemas/responses.py`:

```python
"""Схемы ответов модуля notes."""

from datetime import datetime
from uuid import UUID

from app.kernel.schemas import BaseResponse


class NoteResponse(BaseResponse):
    """Заметка целиком."""

    id: UUID
    title: str
    body: str
    owner_id: UUID | None
    created_at: datetime
    updated_at: datetime
```

`updated_at` отдаётся, если у модуля есть PATCH: без неё клиент не может
понять, применилась ли правка. Значение обновляет `TimestampMixin`
(`onupdate=func.now()`), а `eager_defaults` в `Base` возвращает новое значение
тем же запросом — перечитывать строку после `CRUD.update` не нужно.

`BaseResponse` объявлен с `from_attributes=True`, поэтому ответ собирается прямо
из ORM-объекта: `NoteResponse.model_validate(note)`. Внутренние поля (ключ в
бакете, имя очереди, внутренние счётчики) наружу не отдаются.

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

## Шаг 6. Подписчик

`subscribers.py` создаётся, только если модуль слушает **чужие** события.

**На собственное событие модуль не подписывается.** Эффект, нужный сразу после
записи, делается прямым вызовом в том же сервисе; подписка на себя гоняет факт
через outbox, брокер и воркер только затем, чтобы вернуться в тот же пакет.
Единственное оправдание — эффект обязан выполняться в воркере и переживать
повторы (медленная рассылка, тяжёлый пересчёт). Тогда так и напиши в
`.claude/CLAUDE.md` модуля, иначе следующий читатель примет это за образец.

**Чужое событие нельзя импортировать.** Контракт import-linter
«Business modules never import each other» ломается на любом импорте из
соседнего модуля, включая его `events.py`:

```
app.modules.tickets is not allowed to import app.modules.storage:
- app.modules.tickets.subscribers -> app.modules.storage.events (l.6)
```

Третий «модуль-контракт» в `app/modules/` не спасает: независимость запрещает
и его. Контракт между модулями — это **топик**, а не класс. Подписчик объявляет
у себя своё событие с тем же `topic` и только теми полями, которые ему нужны;
лишнее в полезной нагрузке pydantic отбросит:

```python
"""Подписчики модуля notes."""

from typing import ClassVar
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.events.bus import DomainEvent, subscribe

_logger = structlog.get_logger("app.modules.notes")


class FileArrived(DomainEvent):
    """Файл принят хранилищем.

    Топик чужой, класс свой: импортировать `app.modules.storage.events`
    запрещено контрактом независимости модулей.
    """

    topic: ClassVar[str] = "file.confirmed"

    file_id: UUID
    key: str


@subscribe(FileArrived)
async def attach_file(event: FileArrived, _session: AsyncSession) -> None:
    """Приложить загруженный файл к заметке.

    Сессия та же, в которой стоит отметка `processed_messages`: данные
    подписчика и отметка коммитятся вместе. Имя аргумента начинается с
    подчёркивания, потому что этот подписчик в базу не пишет.
    """
    _logger.info("notes.attachment_seen", file_id=str(event.file_id), key=event.key)
```

Класс события живёт в `subscribers.py`, а не в `events.py`: `events.py` — это
то, о чём модуль **сообщает**. Реестр такому раскладу не мешает:
`build_event_registry` закрепляет топик только за классами, на которые кто-то
подписан, поэтому класс владельца и класс подписчика не конфликтуют. Два
**подписанных** класса на один топик роняют процесс на старте.

- декоратор `@subscribe(Event)` обязателен: функция в `Module.subscribers` без
  него роняет процесс на старте с понятным сообщением;
- сигнатура всегда `(event, session)`; если сессия не нужна — назови аргумент
  `_session`, иначе ruff справедливо пожалуется на неиспользуемый аргумент;
- **подписчик обязан быть идемпотентным**: доставка at-least-once;
- исключение подписчика откатывает транзакцию вместе с отметкой об обработке, и
  сообщение приезжает снова. Это правильно: частично применённое событие хуже
  повтора.

## Шаг 7. Задачи

`tasks.py` — если есть фоновая работа:

```python
"""Периодические задачи модуля notes."""

from datetime import timedelta

from app.kernel.db import session as db_session
from app.modules.notes.services import purge_old_notes
from app.platform.taskiq import schedule


@schedule(interval=timedelta(hours=1))
async def purge_notes() -> int:
    """Удалить заметки старше срока хранения."""
    return await purge_old_notes(session_factory=db_session.session_factory)
```

- `@schedule(cron=...)` или `@schedule(interval=...)`; расписание берётся из
  настроек модуля, а не зашивается числом;
- фабрика сессий читается из модуля (`db_session.session_factory`), а не
  импортируется по имени: тесты подменяют глобаль ядра;
- имя задачи в очереди — `<модуль>.<функция>`, оно живёт дольше выкатки;
- задача переживает параллельный запуск в нескольких воркерах
  (`FOR UPDATE SKIP LOCKED`) и не падает целиком из-за одного элемента: отказ
  по элементу — запись в лог и следующий элемент;
- клиентов внешних сервисов задача создаёт сама на каждый запуск: `lifespan`
  модуля поднимает только приложение FastAPI, воркер его не исполняет.

Образец с обоими видами расписания и созданием клиента —
`modules/storage/tasks.py`.

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
но это осознанное решение модуля, и его место в его `.claude/CLAUDE.md`.

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

## Шаг 9. Настройки

Если у модуля есть лимиты, TTL или расписания — класс настроек живёт рядом с
владельцем, в `services.py`:

```python
class NotesSettings(BaseSettings):
    """Лимиты и расписания модуля notes."""

    model_config = SettingsConfigDict(
        env_prefix="notes_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    retention_days: int = Field(default=90, ge=1)


#: Единственный экземпляр настроек процесса.
notes_settings = NotesSettings()
```

- `os.getenv` и `os.environ` запрещены линтером: конфигурация читается только
  через pydantic-settings;
- **каждая переменная дописывается в `.env.example`** — в свою секцию, с
  комментарием, зачем она и чем грозит неудачное значение. Дефолт в коде обязан
  совпадать со значением в файле;
- класс перечисляется в манифесте (`settings=NotesSettings`).

## Шаг 10. Манифест

`module.py`:

```python
"""Манифест модуля notes."""

from typing import Final

from app.kernel.registry import Module
from app.modules.notes.handlers import router

notes_module: Final = Module(
    name="notes",
    router=router,
    # prefix не задан: адрес модуля — /notes. Задавай явно, если ресурс
    # называется иначе, чем модуль (модуль storage вешает ручки на /files).
    models="app.modules.notes.models",
)
```

Указывай только те поля, что нужны; обязательно одно — `name`.

| Поле | Что задаёт |
| --- | --- |
| `name` | имя модуля; обязано совпадать с именем каталога |
| `router` | `APIRouter` модуля. Нет его — у модуля нет HTTP |
| `prefix` | адрес ресурса, если он не `/<name>`. `""` вешает ручки в корень |
| `settings` | класс настроек модуля (шаг 9) |
| `models` | import-путь пакета моделей: по нему alembic собирает метаданные |
| `subscribers` | функции, помеченные `@subscribe(...)` (шаг 6) |
| `tasks` | корутины, помеченные `@schedule(...)`; исполняет только воркер |
| `consumers` | `ConsumerDecl`: очередь чужого сервиса → обработчик |
| `topology` | `TopologyDecl`: обмен, привязка и очередь внешнего обмена |
| `lifespan` | долгоживущие клиенты; поднимается **только** в процессе uvicorn |

Поля `TopologyDecl` и `ConsumerDecl` (`dead_letter`, `retry_ttl_ms`, `prefetch`,
`requires_idempotency`) с объяснением каждого умолчания — в
`src/app/kernel/registry.py`; читай их там, а не угадывай.

`lifespan` нужен, только если модулю требуется долгоживущий клиент (соединение
с брокером, клиент S3). Воркер его не исполняет, поэтому задачи создают своих
клиентов сами. Образец — `modules/storage/module.py`.

`__init__.py` модуля — одна строка докстринга:

```python
"""Модуль notes: заметки пользователей."""
```

## Шаг 11. Регистрация в `MODULES`

`src/app/modules/__init__.py` — импорт манифеста и его имя в кортеже:

```python
from app.modules.notes.module import notes_module
...
MODULES: Final[tuple[Module, ...]] = (health_module, storage_module, notes_module)
```

Эти две строки — **единственная правка вне каталога модуля** (не считая
`.env.example`, если у модуля есть настройки, и файла миграции). Роутер,
метаданные Alembic, задачи, подписчики и топология подключатся сами.

Пакет без записи в `MODULES` роняет
`tests/test_registry.py::test_every_module_on_disk_is_registered`, запись без
пакета — `::test_every_registered_module_exists_on_disk`.

## Шаг 12. Миграция

Полный порядок работы со схемой, включая переименования и проверку отката, —
скилл `db-migration`. Ниже — тот же порядок в объёме, нужном новому модулю.

Autogenerate ходит в базу, поэтому Postgres должен быть поднят и накатан.
Alembic запускается **с хоста** и знает только про базу — образ приложения ему
не нужен:

```bash
make up                  # или docker compose up -d --wait postgres — для миграции хватит его
make migrate
make revision m="add notes"
```

**Сразу отформатируй сгенерированный файл** — autogenerate пишет в своём стиле
(одинарные кавычки, длинные строки), и `make check` на нём падает:

```bash
uv run ruff format alembic/versions/<новый файл>.py
```

Затем **прочитай сгенерированный файл**:

- имя таблицы, типы колонок и nullable — те, что задумывались;
- keyset-индекс на месте и **направление сортировки сохранено**:
  ```python
  op.create_index(
      "ix_notes_keyset",
      "notes",
      [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
      unique=False,
  )
  ```
  Индекс без `DESC` бесполезен для `ORDER BY created_at DESC, id DESC`;
- переименование колонки autogenerate не распознаёт и превращает в
  «удалить + создать» — с потерей данных. Такие правки пишутся руками;
- `downgrade()` действительно возвращает базу к прежнему состоянию: CI
  откатывает всю цепочку до `base` и проверяет, что таблиц не осталось.

Проверь и накати:

```bash
make migrate
uv run alembic check    # «No new upgrade operations detected»
```

`alembic check` не пустая формальность: он ловит расхождение моделей и
миграций, из-за которого `make test` упал бы на создании схемы.

## Шаг 13. Свой `.claude/CLAUDE.md`

`src/app/modules/<name>/.claude/CLAUDE.md` обязателен — без него падает
`tests/test_architecture.py::test_every_module_carries_agent_instructions`.

Это не пересказ кода. Напиши то, чего по коду не видно:

1. **Одна фраза о том, что делает модуль**, и таблица ручек.
2. **Главное правило модуля** — то, нарушение которого сломает его тише всего.
   Для модуля с PATCH это почти всегда `__patchable__`: что клиент вправе
   менять и почему остальное — нет.
3. **Жизненный цикл сущности**, если у неё есть состояния: кто какой статус
   ставит, откуда возврата нет, что происходит при повторном DELETE.
4. **Чего в модуле нет и почему** — список файлов, которых не будет, чтобы
   следующий агент не создал их «для полноты».
5. **События**: что и когда эмитится, кто на это подписан, чего не эмитится.
6. **Индексы**: зачем каждый нужен и какого нет намеренно.
7. **Команды**: как прогнать тесты модуля и как дёрнуть ручки руками.
8. **Если правишь модуль**: 3–5 пунктов «новое X → сделай Y».

Образцы: `src/app/modules/storage/.claude/CLAUDE.md` (полноценный модуль) и
`src/app/modules/health/.claude/CLAUDE.md` (модуль без моделей и задач).

## Шаг 14. Тесты

`tests/test_<name>.py`. Заготовка ниже проверяет то, что ломается чаще всего:
ручка создаёт строку, событие уезжает в outbox той же транзакцией, список
листается курсором, PATCH меняет только присланное и не пропускает `null`,
DELETE отвечает 204, а повтор — 404.

```python
"""Модуль notes: создание, событие, список, PATCH и DELETE."""

from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.kernel.db import session as session_module
from app.kernel.events.models import OutboxMessage
from app.modules.notes.models import Note
from app.modules.notes.module import notes_module
from tests.asgi import app_client

NOTE = {"title": "first", "body": "hello"}


@pytest.fixture
async def client(clean_db: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    """Клиент к приложению из одного модуля notes на чистой базе.

    `clean_db`, а не `session`: тесту нужны настоящие транзакции — иначе
    «событие и данные закоммитились вместе» проверить нечем.

    Свою таблицу тест чистит сам: `clean_db` знает только про таблицы,
    перечисленные в `tests/conftest.py::TEST_MODELS`, а строки, оставленные
    соседним тестом, ломают счёт страниц в проверке пагинации.
    """
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(Note))
    async with app_client([notes_module]) as http:
        yield http


async def test_creating_a_note_returns_it(client: AsyncClient) -> None:
    response = await client.post("/notes", json=NOTE)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["title"] == "first"


async def test_creating_a_note_writes_the_event_to_the_outbox(client: AsyncClient) -> None:
    await client.post("/notes", json=NOTE)

    async with session_module.session_factory() as session:
        topics = (await session.scalars(select(OutboxMessage.topic))).all()

    assert list(topics) == ["note.created"]


async def test_unknown_field_is_rejected(client: AsyncClient) -> None:
    """`BaseRequest` объявлен с extra="forbid": опечатка не должна молчать."""
    response = await client.post("/notes", json={**NOTE, "owner_id": "nobody"})

    # Именно UNPROCESSABLE_ENTITY: UNPROCESSABLE_CONTENT появился в 3.13, а
    # проект собирается на 3.12, и mypy это поймает.
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_the_list_is_paginated_by_cursor(client: AsyncClient) -> None:
    for number in range(3):
        await client.post("/notes", json={**NOTE, "title": f"note {number}"})

    first = (await client.get("/notes", params={"limit": 2})).json()
    rest = (await client.get("/notes", params={"cursor": first["next_cursor"]})).json()

    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None


async def test_patch_changes_only_the_fields_sent(client: AsyncClient) -> None:
    created = (await client.post("/notes", json=NOTE)).json()

    patched = (await client.patch(f"/notes/{created['id']}", json={"title": "second"})).json()

    assert patched["title"] == "second"
    assert patched["body"] == created["body"]
    assert patched["updated_at"] > created["updated_at"]


async def test_explicit_null_is_rejected(client: AsyncClient) -> None:
    """`{"title": null}` — 422, а не NULL в NOT NULL-колонке."""
    created = (await client.post("/notes", json=NOTE)).json()

    response = await client.patch(f"/notes/{created['id']}", json={"title": None})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_delete_removes_the_note_and_repeats_answer_404(client: AsyncClient) -> None:
    created = (await client.post("/notes", json=NOTE)).json()

    first = await client.delete(f"/notes/{created['id']}")
    repeat = await client.delete(f"/notes/{created['id']}")

    assert first.status_code == HTTPStatus.NO_CONTENT
    assert not first.content
    assert repeat.status_code == HTTPStatus.NOT_FOUND
    assert (await client.get(f"/notes/{created['id']}")).status_code == HTTPStatus.NOT_FOUND
```

Что учесть:

- фикстуры `clean_db`, `session`, `broker`, `minio_endpoint`, `redis_dsn` живут
  в `tests/conftest.py`; там же объяснено, чем режим `clean_db` (настоящие
  транзакции) отличается от `session` (вложенная с откатом);
- **`clean_db` не знает про таблицу нового модуля.** Он чистит только то, что
  перечислено в `TEST_MODELS`. Либо чисти свою таблицу в собственной фикстуре
  (как в заготовке выше — так правки не выходят за пределы модуля), либо
  добавь модель в `TEST_MODELS` (так сделано для `File` модуля `storage`).
  Не сделав ни того ни другого, получишь тест, который проходит в одиночку и
  падает в полном прогоне;
- приложение собирается через `tests/asgi.py::app_client` из **списка
  манифестов**, а не из глобального `MODULES`: тест модуля не должен зависеть
  от соседей. `lifespan=True` нужен, только если у модуля есть `lifespan`;
- в тестах `assert` разрешён, докстринги не обязательны, но неиспользуемый
  аргумент-фикстуру придётся пометить `# noqa: ARG001`;
- если модуль ходит во внешний сервис — скопируй сторож `guard_transactions` из
  `tests/test_storage.py`: он падает, когда клиент дёргают при открытой
  транзакции.

## Шаг 15. Проверка

Форматируется **только своё**: `ruff format .` прошёлся бы по всему
репозиторию и внёс правки в файлы, о которых никто не просил.

```bash
uv run ruff format src/app/modules/<name> tests/test_<name>.py \
    src/app/modules/__init__.py alembic/versions/<новый файл>.py
make check   # формат, линтер, типы, правила зависимостей
make test    # весь прогон, включая архитектурные тесты (нужен Docker)
```

Оба обязаны быть зелёными **без правок за пределами каталога модуля**.

`make test`, а не `pytest tests/test_<name>.py`: тест модуля, проходящий в
одиночку, вполне может падать в полном прогоне из-за строк, оставленных
соседями.

Перед коммитом пройди скилл `pre-commit`: кроме этих двух команд он проверяет
то, чего линтер не ловит, — нужность `@idempotent`, выбор `emit()` против
`after_commit`, keyset-индекс и полноту `.env.example`.

### Живая проверка

`make up` поднимает `api` и `worker` **из образа, собранного из кода**. Стек,
поднятый до появления модуля, о новых ручках не знает и ответит на них 404 —
для миграции это неважно (alembic ходит с хоста прямо в postgres), а перед
проверкой ручек нужен один из двух вариантов:

```bash
docker compose up -d --build api worker   # пересобрать образ со своим модулем
# либо режим разработки, без пересборки образа:
make run                                  # uvicorn с автоперезагрузкой
make worker                               # соседний терминал, если нужны задачи и релей
```

Дальше — полный цикл ручками; те же команды положи в `.claude/CLAUDE.md` модуля:

```bash
ID=$(curl -s localhost:8000/notes -H 'content-type: application/json' \
  -d '{"title":"first","body":"hello"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
curl -s localhost:8000/notes/$ID
curl -s "localhost:8000/notes?limit=2"                       # next_cursor не null
curl -s -X PATCH localhost:8000/notes/$ID -H 'content-type: application/json' \
  -d '{"title":"second"}'                                    # 200, updated_at сдвинулся
curl -s -X PATCH localhost:8000/notes/$ID -H 'content-type: application/json' \
  -d '{"title":null}'                                        # 422 problem+json
curl -si -X DELETE localhost:8000/notes/$ID | head -1        # 204
curl -s -X DELETE localhost:8000/notes/$ID                   # 404 problem+json
```

Если что-то красное, смотри сюда:

| Симптом | Причина |
| --- | --- |
| `test_every_module_on_disk_is_registered` | забыта запись в `MODULES` |
| `test_every_registered_module_exists_on_disk` | имя в `MODULES` не совпало с каталогом |
| `test_every_module_carries_agent_instructions` | нет `<модуль>/.claude/CLAUDE.md` |
| `test_handlers_never_import_crud` | в `handlers.py` импортирован `CRUD` |
| `test_services_never_raise_http_exceptions` | в `services.py` упомянут `HTTPException` |
| `test_modules_never_commit_the_session` | где-то вызван `session.commit()` |
| `test_uow_dependencies_close_before_the_response` | `Depends(get_uow)` без `scope="function"` |
| `lint-imports`: `Business modules never import each other` | импортирован соседний модуль — в том числе его `events.py` (шаг 6) |
| `lint-imports`: `Layers` | модуль импортирует `app.api` |
| `mypy`: `Incompatible types in assignment` в схеме патча | `field: str = Field(default=None)`; правильно `field: str \| None = Field(default=None, ...)` |
| 500 и `IntegrityError` на PATCH с `null` | в схеме патча нет валидатора, отвергающего явный `null` |
| 409 `Fields are not patchable` на законное поле | поле есть в схеме патча, но забыто в `Model.__patchable__` |
| 404 на новые ручки при живой проверке | контейнер `api` собран до появления модуля: `docker compose up -d --build api worker` |
| тест проходит один, падает в прогоне | таблица модуля не чистится между тестами |
| `ruff format --check` на `alembic/versions/…` | миграция не отформатирована после генерации |
| `UndefinedTable` в тестах модуля | миграция не сгенерирована или не накатана |
| `alembic check` нашёл операции | модель и миграция разъехались |
| `mypy` ругается на `app.state` | нужен `cast(...)`: `app.state` не типизирован |

## Итог: что должно было измениться

```
src/app/modules/<name>/**      новый каталог целиком
src/app/modules/__init__.py    импорт манифеста + его имя в MODULES
alembic/versions/<...>.py      новая миграция
tests/test_<name>.py           тесты модуля
.env.example                   только если у модуля есть настройки
```

Больше ничего. `kernel/config.py`, `alembic/env.py`, `api/router.py`,
`main.py`, `worker.py`, `pyproject.toml` при добавлении модуля не трогаются —
проверь это командой `git status` перед коммитом.
