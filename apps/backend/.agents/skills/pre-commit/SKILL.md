---
name: pre-commit
description: Проверить backend перед коммитом — lint, типы, тесты, миграции и инварианты изменения.
---

# Проверка backend

Рабочий каталог — `apps/backend/`. Сначала `make check` и `make test`
(testcontainers требуют Docker; kernel coverage ≥85%). Недоступность Docker
означает невыполненную проверку, а не успех.

Засчитывай успешные проверки из этой задачи, если после них не менялись
относящиеся к проверке код, конфигурация или окружение. Повторяй после изменений
или ошибки, а не из-за перехода между skills.

Если менялась схема, на отдельной локальной базе без ценных данных проверь
изменённую ревизию; при нескольких ревизиях откатись до их общего предшественника:

```bash
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic check
```

Оба `alembic check` должны быть чистыми; downgrade должен исполняться.
Управление контейнерами и применение миграций стека — через `infra/`.

## Ревью применимых пунктов

- Новый модуль: `MODULES`, локальный AGENTS и тесты.
- Настройка: Settings и `.env.example`, одинаковый default и пояснение.
- Пишущая ручка: явное решение об `@idempotent`; GET/DELETE без него.
- Эффект: обоснован выбор outbox/after_commit и допустимость потери.
- Пагинация: миграция индекса `(created_at DESC, id DESC)`.
- Внешний I/O: тест отсутствия открытой транзакции; образец —
  `tests/test_storage.py::test_s3_calls_never_happen_inside_a_transaction`.

При ошибке читай соответствующее правило по backend AGENTS;
[правило → проверка](references/rule-to-check.md) нужно только для диагностики.
Коммит выполняй через `git-commit`, когда он запрошен пользователем.
