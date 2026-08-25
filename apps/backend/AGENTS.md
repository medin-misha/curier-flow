# Backend

FastAPI + SQLAlchemy 2.0 async + PostgreSQL. Рабочий каталог команд и skills —
`apps/backend/`. Контейнеры запускаются только через `../../infra/`.

Для общей backend-задачи запускай `codex --cd apps/backend`. Для изменения
существующего модуля запускай Codex из `src/app/modules/<name>`: тогда к этой
инструкции добавятся `AGENTS.md` и skills конкретного модуля.

## Команды

| Команда | Что делает |
| --- | --- |
| `make install` | зависимости и git-хуки |
| `make check` | формат, ruff, mypy, import-linter |
| `make test` | pytest с testcontainers и покрытием kernel ≥ 85% |
| `make migrate` | `alembic upgrade head` |
| `make revision m="..."` | autogenerate миграции |
| `make -C ../../infra help` | команды управления стеком |

Перед backend-коммитом обязателен skill `pre-commit`; тестам нужен Docker.

## Неподвижные инварианты

- Слои: `api → modules → platform → kernel`; бизнес-модули не импортируют
  друг друга и общаются доменными событиями.
- Состав сервиса задаёт только `src/app/modules/__init__.py::MODULES`.
- HTTP-ручка разбирает запрос и собирает ответ; бизнес-логика и `CRUD` живут
  в `services.py`.
- Пишущая ручка использует `Depends(get_uow, scope="function")`, читающая —
  `get_ro_session`; `session.commit()` в модуле запрещён.
- В открытой транзакции нет S3, HTTP, RabbitMQ и `kiq()`.
- Наружу выходят ошибки RFC 9457; бизнес-код поднимает `AppError`, не
  `HTTPException`.
- Пагинация только keyset по `(created_at DESC, id DESC)` и с совпадающим
  индексом.
- Окружение читается через pydantic-settings; новая настройка одновременно
  появляется в `.env.example` с тем же дефолтом.
- Схема БД меняется только миграцией.
- TaskIQ выполняет нашу фоновую работу, RabbitMQ напрямую — обмен с внешними
  сервисами; оба механизма живут только в `worker.py`.

## Контекст по изменению

Подробные правила лежат в `.agents/rules/`. Читай только строки, относящиеся к
реальному изменению:

| Правило | Когда читать |
| --- | --- |
| `layers.md` | меняются импорты, границы слоёв, registry или entrypoint |
| `module-layout.md` | создаётся модуль или меняется ответственность handlers/services/module |
| `transactions.md` | меняются Uow/RoSession, сервис с записью или внешний I/O |
| `events.md` | `emit`, `after_commit`, `events.py` или `subscribers.py` |
| `background-work.md` | `tasks.py`, `consumers.py`, worker, TaskIQ или RabbitMQ |
| `errors.md` | меняются ошибки, error handlers или публичный контракт отказа |
| `pagination.md` | list-ручка, `list_page`, cursor или keyset-индекс |
| `settings.md` | Settings-класс, config или `.env.example` |
| `migrations.md` | модель, индекс, ограничение или Alembic |
| `idempotency.md` | записывающая ручка, `@idempotent`, повтор сообщения |
| `kernel-and-platform.md` | любой код в `kernel/` или `platform/` |

## Skills

Backend skills находятся в `.agents/skills/` и доступны при запуске из
`apps/backend` или глубже:

| Skill | Когда |
| --- | --- |
| `admin-auth` | Admin/JWT, login/refresh/logout, bootstrap и точечная защита ручек |
| `new-module` | новый бизнес-модуль целиком |
| `background-effect` | событие, уведомление, задача, расписание, чужая очередь |
| `db-migration` | изменение схемы существующего модуля |
| `pre-commit` | проверка перед backend-коммитом |

У существующего модуля обязательно есть собственный `AGENTS.md`. Не используй
`new-module` для его изменения: запусти Codex из каталога модуля и используй
его локальный skill.
