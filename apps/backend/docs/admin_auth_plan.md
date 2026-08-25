# План административного модуля и JWT-аутентификации

Статус: ядро задачи реализовано и проверено; rollout меток по существующим
модулям и пример переменных Compose вынесены в scoped-сессии своих областей.

Этот файл — рабочий источник правды по задаче. После каждого завершённого
этапа чекбокс и журнал в конце файла обновляются в том же изменении.

## Подтверждённые решения

- [x] Модуль называется `admin`, HTTP-префикс — `/admin`.
- [x] Основные модели — `Admin` и `AdminRefreshToken`.
- [x] Access JWT короткоживущий и передаётся как Bearer; refresh JWT хранится
  только в `HttpOnly` cookie.
- [x] Refresh-токены ротируются, в БД хранится только SHA-256 токена, повторное
  использование отзывает всё семейство.
- [x] Первый Admin создаётся при старте API из `.env`, только когда таблица
  `admins` пуста.
- [x] Bootstrap сериализуется PostgreSQL advisory lock и повторно проверяет
  пустоту таблицы внутри транзакции.
- [x] Защита включается точечно на конкретной ручке; отсутствие метки означает
  публичную ручку.
- [x] Создание курьера должно остаться публичным, чтение и изменение курьеров —
  защищёнными. Изменение существующего `courier_module` выполняется отдельно
  из module-scoped сессии по его локальному `AGENTS.md`.
- [x] `platform` не импортирует `admin`; криптография остаётся в
  `kernel/security`, бизнес-проверка Admin — в admin-сервисе.

## Контракт данных

### `admins`

- `id UUID` — UUIDv7 primary key;
- `username VARCHAR(64) NOT NULL UNIQUE` — хранится в lowercase ASCII;
- `hashed_password VARCHAR(512) NOT NULL`;
- `telegram_id BIGINT NULL UNIQUE`;
- `is_active BOOLEAN NOT NULL DEFAULT true`;
- `auth_version INTEGER NOT NULL DEFAULT 1`;
- `created_at`, `updated_at` — timezone-aware server timestamps;
- keyset-индекс `(created_at DESC, id DESC)`.

PATCH меняет только `username` и `telegram_id`. Пароль, активность и
`auth_version` меняются отдельными сервисными операциями.

### `admin_refresh_tokens`

- `id UUID` — `jti` refresh-токена и primary key;
- `admin_id UUID NOT NULL` — FK на `admins`, `ON DELETE CASCADE`;
- `family_id UUID NOT NULL`;
- `token_hash VARCHAR(64) NOT NULL` — SHA-256, plaintext не хранится;
- `auth_version INTEGER NOT NULL`;
- `expires_at TIMESTAMPTZ NOT NULL`;
- `used_at TIMESTAMPTZ NULL`;
- `revoked_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- индексы под поиск по `admin_id`, `family_id` и очистку `expires_at`.

Список refresh-токенов наружу не отдаётся, поэтому keyset-индекс этой таблице
не нужен.

## HTTP-контракт

Публичные ручки:

- `POST /admin/auth/login`;
- `POST /admin/auth/refresh`;
- `POST /admin/auth/logout`.

Защищённые ручки:

- `GET /admin/admins/me`;
- `POST /admin/admins`;
- `GET /admin/admins`;
- `GET /admin/admins/{admin_id}`;
- `PATCH /admin/admins/{admin_id}`;
- `POST /admin/admins/{admin_id}/activate`;
- `POST /admin/admins/{admin_id}/deactivate`;
- `POST /admin/admins/{admin_id}/reset-password`.

Login/refresh возвращают access token и его TTL в JSON. Refresh token ставится
только cookie с `HttpOnly`, настраиваемыми `Secure`/`SameSite` и path
`/admin/auth`; в JSON и логах его нет. Token responses явно запрещают
кеширование через `Cache-Control: no-store` и `Pragma: no-cache`.

## Правила безопасности

- Неверный username, пароль и неактивный Admin дают одинаковый `401`.
- Для неизвестного username выполняется Argon2-проверка dummy hash.
- После успешного входа устаревший Argon2 hash обновляется.
- Access содержит `kind=admin` и `auth_version`; admin-зависимость сверяет их с
  актуальной строкой.
- Refresh проверяется по подписи, `jti`, SHA-256, Admin и `auth_version`.
- Ротация блокирует строку `SELECT ... FOR UPDATE`.
- Повтор использованного refresh отзывает всё семейство и возвращает `401`
  уже после фиксации отзыва.
- Смена пароля увеличивает `auth_version` и отзывает все refresh-токены Admin.
- Деактивация отзывает все refresh-токены.
- Нельзя деактивировать себя или последнего активного Admin; операция
  сериализуется advisory lock.
- Login и refresh не используют `@idempotent`, потому что сохранённый ответ
  раскрыл бы токен/cookie в `idempotency_keys`.
- Создание Admin использует `@idempotent`; reset-password не использует его,
  чтобы новый пароль не участвовал в долговременном HTTP replay-контракте.
- Пароли, JWT, cookie и hashes не логируются.
- Все ошибки выходят RFC 9457 через `AppError`.

## Bootstrap через `.env`

Настройки с `env_prefix="admin_"`:

- `ADMIN_BOOTSTRAP_USERNAME` — пустая строка по умолчанию;
- `ADMIN_BOOTSTRAP_PASSWORD` — пустой `SecretStr` по умолчанию;
- `ADMIN_BOOTSTRAP_TELEGRAM_ID` — пустое значение/`None`;
- `ADMIN_REFRESH_COOKIE_NAME=admin_refresh`;
- `ADMIN_REFRESH_COOKIE_SECURE=false` локально, в prod обязательно `true`;
- `ADMIN_REFRESH_COOKIE_SAMESITE=strict`;
- `ADMIN_REFRESH_CLEANUP_CRON=17 4 * * *`.

Lifespan API открывает короткую транзакцию, берёт advisory lock и проверяет
`admins`. Если Admin уже существует, bootstrap-настройки не используются. Если
таблица пуста, username/password обязаны быть непустыми; иначе старт падает с
безопасной ошибкой конфигурации. Несколько API-реплик создают ровно одну строку.

Bootstrap не выполняется worker-процессом и не публикует событий.

## Точечная защита ручек

- В `kernel/security` добавляется чистая метка `@authenticated`, не знающая о
  FastAPI.
- `app/api/authentication.py` после сборки приложения находит помеченные
  маршруты и подключает проверку access Bearer по тому же паттерну, что
  `install_idempotency`.
- Метка требует валидный access JWT с `kind=admin`, устанавливает `actor_id` и
  отвергает отсутствие токена, refresh-токен и неверную подпись.
- Публичная ручка метки не имеет. Защита видна рядом с объявлением endpoint,
  а не задаётся хрупким списком URL.
- Административные endpoints дополнительно получают `CurrentAdmin`, который
  проверяет существование, `is_active` и `auth_version` в БД.

## Фоновая работа

- `admin.purge_expired_refresh_tokens` — периодическая TaskIQ-задача.
- Удаляет строки с `expires_at < now()` короткой DB-транзакцией.
- Регистрируется только через `Module.tasks`; `worker.py` не меняется.
- События/outbox, subscribers и RabbitMQ consumers модулю не нужны.

## Этапы реализации

- [x] 1. Зафиксировать план и проверить границы существующих изменений.
- [x] 2. Добавить kernel-метку и API-подключение точечной аутентификации с
  изолированными тестами.
- [x] 3. Создать каркас `admin`, модели, schemas, settings и `AGENTS.md`.
- [x] 4. Реализовать Admin CRUD, login, CurrentAdmin и password rehash.
- [x] 5. Реализовать refresh storage, rotation, reuse detection и logout.
- [x] 6. Реализовать startup bootstrap из `.env` с защитой от гонки.
- [x] 7. Добавить TaskIQ-очистку и регистрацию модуля.
- [x] 8. Создать и проверить Alembic-миграцию.
- [x] 9. Добавить тесты критериев готовности и негативных сценариев.
- [x] 10. Отформатировать только изменённые файлы, выполнить `make check`,
  `make test`, `alembic check` и ревью инвариантов `pre-commit`.
- [ ] 11. Применить `@authenticated` к нужным ручкам существующих модулей в
  отдельных module-scoped сессиях; создание курьера оставить публичным.
- [ ] 12. Продублировать `ADMIN_*` в `infra/.env.example` из infra-scoped
  сессии. Compose уже передаёт весь `infra/.env` в API через `env_file`.

## Критерии готовности

- [x] В БД нет plaintext-паролей и plaintext refresh-токенов.
- [x] Duplicate username/telegram ID даёт `409`.
- [x] Unknown username и wrong password дают одинаковый `401` и выполняют
  Argon2 verification.
- [x] Успешный login обновляет устаревший hash.
- [x] Access принимается защищённой ручкой, refresh вместо access отвергается.
- [x] Missing/disabled/version-mismatched Admin отвергается `CurrentAdmin`.
- [x] Refresh ротируется; старый токен не создаёт вторую действующую ветку.
- [x] Reuse старого refresh отзывает семейство.
- [x] Два параллельных refresh не оставляют две активные ветки.
- [x] Нельзя деактивировать себя и последнего активного Admin.
- [x] Bootstrap при пустой таблице создаёт ровно одного Admin, при непустой —
  no-op, при пустых credentials — роняет startup.
- [x] Список Admin использует keyset pagination и matching index.
- [x] Cleanup удаляет истёкшие refresh-токены.
- [x] Новые settings присутствуют в `.env.example` с теми же defaults.
- [x] Миграция проходит upgrade, `alembic check` и downgrade.
- [x] `make check` и полный `make test` зелёные.

## Журнал выполнения

- 2026-08-25: пользователь подтвердил модели, HTTP-контракт, token transport,
  правила безопасности и критерии готовности; bootstrap изменён на startup из
  `.env`; защита изменена с module-wide на точечную endpoint-метку.
- 2026-08-25: план записан; обнаруженные пользовательские изменения
  `courier_module` и `infra` исключены из текущего change scope.
- 2026-08-25: добавлены чистая метка `@authenticated`, API-инсталлятор и
  проверки public/protected, actor context, actor kind и access/refresh;
  20 целевых тестов зелёные.
- 2026-08-25: собран и зарегистрирован модуль `admin`: модели, HTTP-схемы,
  CRUD, CurrentAdmin, Argon2 login/rehash, stateful refresh rotation/logout,
  startup bootstrap под advisory lock и TaskIQ cleanup.
- 2026-08-25: миграция проверена циклом downgrade/upgrade и `alembic check`;
  `make check` зелёный, полный suite — 482 теста, общее покрытие 95%, kernel
  100%. Pre-commit review инвариантов замечаний не оставил.
- 2026-08-25: первый partial commit был отложен из-за незавершённого merge.
  Merge с `origin/main` позже завершён отдельным коммитом `75ee345`; admin/auth
  остаётся самостоятельным логическим изменением.
