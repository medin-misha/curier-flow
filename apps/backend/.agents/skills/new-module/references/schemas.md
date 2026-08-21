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
