---
paths:
  - "src/app/modules/**/*.py"
---

# Состав и слои бизнес-модуля

## Реестр модулей — единственный источник правды

`src/app/modules/__init__.py` перечисляет манифесты. Из этого списка собираются
роутер, lifespan, метаданные Alembic, задачи TaskIQ, топология брокера и
подписчики. Автодискавери по файловой системе нет намеренно: состав сервиса не
должен зависеть от результата обхода каталогов.

- модуль подключается **одной строкой** в `MODULES` — и больше нигде;
- пакет в `src/app/modules/`, которого нет в `MODULES`, — ошибка;
- имя в `MODULES` без каталога `src/app/modules/<name>/module.py` — тоже ошибка;
- модуль ничего не регистрирует на импорте: манифест только описывает себя.

**Проверяют:** `tests/test_registry.py::test_every_module_on_disk_is_registered`,
`::test_every_registered_module_exists_on_disk`,
`tests/test_architecture.py::test_every_module_package_is_registered`.

## Слои внутри модуля

```
src/app/modules/<name>/
  handlers.py            только HTTP
  services.py            бизнес-логика
  models/                ORM-модели (пакет, не файл)
  schemas/requests.py    что принимаем
  schemas/responses.py   что отдаём
  events.py              доменные события модуля       (если они есть)
  subscribers.py         обработчики чужих событий     (если они есть)
  tasks.py               периодические и отложенные задачи (если они есть)
  consumers.py           обработчики сообщений извне   (если они есть)
  module.py              манифест Module
  .claude/CLAUDE.md      правила модуля для агента
```

Файла, которому нечего содержать, быть не должно: пустая заглушка выглядит как
незаконченная работа и провоцирует дописать логику туда, где её не должно быть.
Образец — модуль `health`: у него нет ни `models/`, ни `subscribers.py`, и в
его `.claude/CLAUDE.md` объяснено почему.

`handlers.py`:

- не импортирует `CRUD` и вообще ничего из `app.kernel.db.crud`;
- не вызывает `session.commit()`;
- не ходит в S3, RabbitMQ и по HTTP наружу;
- не содержит бизнес-правил: разобрал запрос, позвал сервис, собрал ответ.

`services.py`:

- единственное место, где вызывается `CRUD` и `emit()`;
- не знает про HTTP: `HTTPException` запрещён, поднимаются наследники
  `AppError` из `app.kernel.errors`;
- получает сессию (или фабрику сессий) и клиентов аргументами, не создаёт их
  внутри.

**Проверяют:** `tests/test_architecture.py::test_handlers_never_import_crud`,
`::test_services_never_raise_http_exceptions`,
`::test_modules_never_commit_the_session`,
`::test_every_module_carries_agent_instructions`; `make check` — ruff
`banned-api` запрещает `HTTPException` во всём проекте, кроме `app/api/errors.py`.

Новый модуль пишется скиллом `new-module`, а не руками.
