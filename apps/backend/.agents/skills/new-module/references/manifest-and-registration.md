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
