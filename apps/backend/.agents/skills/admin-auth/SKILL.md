---
name: admin-auth
description: Изменить или применить административную JWT-аутентификацию backend — Admin/AdminRefreshToken, login/refresh/logout, bootstrap первого админа, CurrentAdmin, @authenticated и выбор public/protected endpoints. Применяй при любых изменениях admin credentials, token flow или защиты HTTP-ручек; не применяй к авторизации курьеров как самостоятельных пользователей.
---

# Административная аутентификация

Рабочий каталог относительных путей — `apps/backend/`. Сначала полностью
прочитай [mechanism.md](references/mechanism.md): это поддерживаемое описание
текущего механизма и его security boundaries.

## Выбери область до изменения

- Меняется `src/app/modules/admin/**` — работай из
  `src/app/modules/admin/` с его `AGENTS.md`.
- Защищаются ручки существующего бизнес-модуля — работай из каталога этого
  модуля с его локальными инструкциями; публичные endpoints не помечай.
- Меняются общие marker/install primitives в `kernel` или `api` — работай из
  `apps/backend/` и прочитай `.agents/rules/layers.md` и
  `.agents/rules/kernel-and-platform.md`.

Если основная область изменилась, начни новую сессию с её рабочим каталогом;
не полагайся на `cd` в отдельной shell-команде для смены project context.

## Подключи правила реального изменения

- DB-модель или индекс — `.agents/rules/migrations.md` и skill
  `db-migration`.
- Login, refresh, bootstrap или другой сервис с записью —
  `.agents/rules/transactions.md`.
- Публичная ошибка/HTTP-контракт — `.agents/rules/errors.md`.
- Cookie, bootstrap или cron setting — `.agents/rules/settings.md` и тот же
  default в `.env.example`.
- Новая пишущая ручка — `.agents/rules/idempotency.md`; решение об
  `@idempotent` должно быть явным.
- Фоновая очистка — `.agents/rules/background-work.md` и skill
  `background-effect`.

## Неподвижные auth-инварианты

- Access — короткоживущий Bearer JWT; refresh — только `HttpOnly` cookie с
  узким path. Ни пароль, ни plaintext refresh не сохраняются и не логируются.
- Неизвестный username проходит Argon2-проверку dummy hash и получает тот же
  `401`, что неверный пароль или неактивный Admin.
- Успешный login обновляет устаревший Argon2 hash.
- Refresh одноразовый: строка блокируется `FOR UPDATE`, новый токен остаётся в
  той же family, reuse отзывает всю family. Отзыв коммитится до выброса `401`.
- Смена пароля увеличивает `auth_version`; смена пароля и деактивация отзывают
  все refresh-сессии Admin.
- Bootstrap создаёт Admin только при пустой таблице и только в API lifespan,
  под transaction-scoped PostgreSQL advisory lock. Worker его не выполняет.
- `@authenticated` ставится точечно. Отсутствие marker означает публичную
  ручку; нельзя вводить списки URL или module-wide защиту как второй источник
  правды.
- Admin CRUD использует `CurrentAdmin` и проверяет строку БД; общий marker
  сознательно следует TTL access-токена и не делает DB lookup.
- Login/refresh не идемпотентны: replay storage раскрыл бы credentials.
  Создание Admin идемпотентно; reset-password не сохраняет replay с паролем.

Если предлагаемое изменение нарушает эти свойства, сначала явно опиши новую
модель угроз и получи подтверждение пользователя. Не ослабляй их как локальный
рефакторинг.

## Документация и проверка

При изменении поведения обнови
`references/mechanism.md`, HTTP schemas/OpenAPI metadata, `.env.example` и
тест соответствующего негативного сценария в том же change set.

Минимум перед завершением:

```bash
make check
make test
uv run alembic check  # если затронуты модели или миграции
```

Затем используй skill `pre-commit`.
