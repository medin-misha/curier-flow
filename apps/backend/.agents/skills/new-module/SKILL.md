---
name: new-module
description: Создать новый backend-модуль с API, манифестом, миграциями и тестами. Только если каталога модуля ещё нет.
---

# Создание бизнес-модуля

Рабочий каталог — `apps/backend/`. Сначала прочитай `.agents/rules/layers.md`,
`.agents/rules/module-layout.md` и `.agents/rules/transactions.md`.

## 1. Определи состав

Уточни имя и URL ресурса, поля клиента и сервера, операции, изменяемые поля,
события, подписки, фоновые задачи и настройки. Затем прочитай
[planning-and-layout.md](references/planning-and-layout.md).

Не создавай файлы без содержания. Всегда нужны пакет модуля, `module.py`,
`AGENTS.md` и тесты; остальное определяется функциями модуля.

## 2. Подключи только нужные части

- Своя таблица → [models.md](references/models.md).
- Request/response или PATCH → [schemas.md](references/schemas.md).
- CRUD-сервис или своё событие →
  [events-and-services.md](references/events-and-services.md); при побочном
  эффекте сначала используй skill `background-effect`.
- Подписка на чужое событие → [subscribers.md](references/subscribers.md).
- TaskIQ-задача → [tasks.md](references/tasks.md) и skill `background-effect`.
- HTTP API → [handlers.md](references/handlers.md).
- Настройки → [settings.md](references/settings.md) и `.agents/rules/settings.md`.
- Манифест и `MODULES` →
  [manifest-and-registration.md](references/manifest-and-registration.md).
- Изменение схемы → skill `db-migration`; справочный пример нового модуля —
  [migrations.md](references/migrations.md).
- Контекст нового модуля → [module-context.md](references/module-context.md).
- Тесты → [testing.md](references/testing.md).

## 3. Границы изменения

Новый модуль обычно меняет только:

- `src/app/modules/<name>/**`;
- импорт и элемент в `src/app/modules/__init__.py`;
- миграцию;
- `tests/test_<name>.py`;
- `.env.example`, только если появились настройки.

Перед завершением прочитай [change-scope.md](references/change-scope.md) и
[verification.md](references/verification.md), затем используй `pre-commit`.
Не правь `kernel`, `api/router.py`, `alembic/env.py`, `main.py` или `worker.py`
для обычного подключения модуля.
