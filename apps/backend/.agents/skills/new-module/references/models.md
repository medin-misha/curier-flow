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
