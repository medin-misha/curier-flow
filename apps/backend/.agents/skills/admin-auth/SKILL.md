---
name: admin-auth
description: Backend Admin JWT — защита HTTP-ручек, login/refresh/logout, credentials и bootstrap. Не авторизация курьеров.
---

# Административная аутентификация

Команды — из `apps/backend/`; инструкции — AGENTS затронутого модуля.
Читай только нужный контракт:

- Защита endpoint, marker, CurrentAdmin — [защита ручек](references/endpoint-protection.md).
- Login/refresh/logout, модели аккаунтов, password, cookie/CSRF —
  [токены](references/token-flow.md) и [защита ручек](references/endpoint-protection.md).
- Bootstrap, startup, cleanup — [bootstrap/retention](references/bootstrap-and-retention.md).
- Изменение механизма — также [сценарии проверки](references/verification.md).

## Общие security-инварианты

- Access — Bearer JWT; refresh — HttpOnly cookie с узким path.
  Пароли и plaintext refresh не сохраняются и не логируются.
- Неизвестный username проверяется через dummy Argon2 hash; отказ одинаковый
  для неизвестного, неактивного Admin и неверного пароля; login обновляет hash.
- Refresh одноразовый, с блокировкой строки; reuse отзывает family.
  Revoke коммитится до `401`. Смена пароля увеличивает `auth_version`;
  смена пароля/деактивация отзывают refresh-сессии.
- Bootstrap — только API lifespan, пустая таблица и transaction advisory lock.
- `@authenticated` — точечный marker без DB lookup; действует TTL access.
  Admin CRUD требует `CurrentAdmin` с проверкой строки БД.
- Login/refresh не идемпотентны; создание Admin идемпотентно;
  reset-password не сохраняет replay с паролем.

Изменение этих границ требует явной модели угроз и подтверждения пользователя.

## Реализация и проверка

Правила по затронутым файлам выбирай по backend AGENTS. Для модели —
`db-migration`, фонового эффекта — `background-effect`. Kernel/API primitives
требуют `layers.md` и `kernel-and-platform.md`.

Обнови затронутый reference, HTTP schemas/OpenAPI, env и негативные тесты.
Выполни `pre-commit` (make check/test, проверки миграций при изменении схемы).
Уже успешные проверки текущего состояния не запускай повторно.
