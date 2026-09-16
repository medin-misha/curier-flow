# Backend

FastAPI, SQLAlchemy async, PostgreSQL. Применяются [общие правила](../../AGENTS.md);
прочитай их, если ещё не загружены. Для существующего модуля читай его AGENTS.
Команды выполняй из `apps/backend/`; API, worker и контейнеры — через `infra/`.

## Проверка

`make install` — зависимости и хуки; `make check` — формат, lint, типы и
импорты; `make test` — pytest/testcontainers (нужен Docker, kernel coverage ≥85%).
Миграция: `make revision m="..."`; применение: `make -C ../../infra migrate`.
Перед backend-коммитом используй `pre-commit`; уже успешные проверки актуального
состояния повторять не нужно.

## Инварианты

- Слои `api → modules → platform → kernel`; бизнес-модули не импортируют
  друг друга, общаются событиями. Состав — `modules/__init__.py::MODULES`.
- HTTP только разбирает запрос/ответ; бизнес-логика и CRUD — в services.
- Запись: `Depends(get_uow, scope="function")`; чтение: `get_ro_session`.
  `session.commit()` в модулях запрещён; внешний I/O внутри транзакции запрещён.
- Ошибки: `AppError` → RFC 9457, не `HTTPException` из бизнес-кода.
- Пагинация: keyset `(created_at DESC, id DESC)` с соответствующим индексом.
- Settings через pydantic-settings; новый параметр — также в `.env.example`
  с тем же default. Изменение схемы — только миграцией.
- TaskIQ — наша работа, RabbitMQ — внешний обмен; оба только в `worker.py`.

## Контекст по задаче

Из `.agents/rules/` читай только нужные файлы:

| Изменение | Правило |
| --- | --- |
| Импорты, registry, entrypoint | `layers.md` |
| Структура модуля, handlers/services | `module-layout.md` |
| Запись, Uow/RoSession, внешний I/O | `transactions.md` |
| emit/after_commit, подписчик | `events.md` |
| TaskIQ, consumer, worker | `background-work.md` |
| Ошибки | `errors.md` |
| Список, cursor, индекс | `pagination.md` |
| Settings, env | `settings.md` |
| Модель, Alembic | `migrations.md` |
| Пишущая ручка, replay | `idempotency.md` |
| kernel/platform | `kernel-and-platform.md` |

Skills в `.agents/skills/`: `admin-auth` — JWT/защита ручек;
`background-effect` — выбор фонового эффекта; `db-migration` — схема БД;
`new-module` — только новый модуль; `pre-commit` — проверка перед коммитом.
