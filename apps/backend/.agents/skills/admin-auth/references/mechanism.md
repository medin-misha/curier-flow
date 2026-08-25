# Механизм административной аутентификации

Этот reference — living contract административной аутентификации backend.
Обновляй его вместе с изменением token flow, моделей, публичных endpoints,
bootstrap или семантики `@authenticated`.

## Границы архитектуры

| Ответственность | Владелец |
| --- | --- |
| Argon2id и JWT encode/decode | `app/kernel/security/` |
| Чистая endpoint-метка `@authenticated` | `app/kernel/security/authentication.py` |
| Bearer transport и подключение marker | `app/api/authentication.py` |
| Admin, refresh storage и бизнес-проверки | `app/modules/admin/` |
| Состав сервиса | `app/modules/__init__.py::MODULES` |

Направление зависимостей остаётся `api → modules → platform → kernel`.
`platform` не знает об Admin, бизнес-модули не импортируют `admin` друг у
друга, а `kernel` не импортирует FastAPI.

## Два уровня проверки

### `@authenticated`

Marker используется любым бизнес-модулем для точечной защиты ручки. API-слой:

1. требует `Authorization: Bearer <access JWT>`;
2. проверяет подпись, TTL и `typ=access` через kernel;
3. требует claim `kind=admin`;
4. записывает `sub` в `actor_id` request context.

Marker не ходит в БД. Поэтому деактивированный Admin сохраняет доступ к таким
ручкам до истечения уже выданного access JWT; при текущем default это не более
`JWT_ACCESS_TTL=900` секунд. Это осознанная граница stateless access-токена.

Каноническое объявление:

```python
from app.kernel.security.authentication import authenticated


@router.get("/{item_id}")
@authenticated
async def retrieve(...) -> ItemResponse:
    ...
```

Публичная ручка не имеет marker. Например, форма создания курьера остаётся
публичной, а чтение/изменение помечаются отдельно. Не поддерживай параллельный
allowlist/denylist URL: политика должна быть видна рядом с endpoint.

### `CurrentAdmin`

Административные endpoints используют зависимость `CurrentAdmin`. Кроме
криптографической проверки она загружает `Admin` и требует:

- `kind=admin`;
- целочисленный `auth_version`, совпадающий со строкой;
- существующий активный Admin.

Так смена пароля и деактивация закрывают admin surface немедленно, не дожидаясь
TTL access-токена.

## Модели данных

### `admins`

- UUIDv7 `id`;
- уникальный lowercase ASCII `username` длиной до 64;
- `hashed_password` только с Argon2id hash;
- необязательный уникальный положительный `telegram_id`;
- `is_active`, `auth_version`;
- timezone-aware `created_at`, `updated_at`;
- keyset index `(created_at DESC, id DESC)`.

PATCH меняет только username и Telegram ID. Пароль и активность имеют
отдельные операции. Физического DELETE Admin нет, чтобы не терять audit
identity и случайно не удалить последний доступ.

### `admin_refresh_tokens`

- `id` равен подписанному `jti` refresh JWT;
- FK `admin_id` с `ON DELETE CASCADE`;
- `family_id` связывает последовательность ротаций;
- `token_hash` — SHA-256 полного JWT, plaintext отсутствует;
- снимок `auth_version`;
- `expires_at`, `used_at`, `revoked_at`, `created_at`;
- индексы для admin/family revoke и retention по expiry.

Использованные и отозванные строки сохраняются до `expires_at`, иначе reuse
старого токена нельзя было бы обнаружить.

## Token flows

### Login

`POST /admin/auth/login` принимает нормализованный username и пароль:

1. загружает Admin по username;
2. всегда вызывает Argon2 verify — с настоящим или статическим dummy hash;
3. одинаково отвечает `401 invalid-credentials` для неизвестного username,
   неверного пароля и неактивного Admin;
4. при необходимости rehash'ит пароль текущими параметрами;
5. создаёт новую refresh family и сохраняет только SHA-256 refresh JWT;
6. возвращает access JWT и TTL в JSON, refresh ставит в cookie.

Token response содержит `Cache-Control: no-store` и `Pragma: no-cache`.

### Refresh rotation

`POST /admin/auth/refresh` читает refresh только из cookie:

1. проверяет подпись, TTL и `typ=refresh`;
2. находит строку по `jti` и блокирует `SELECT ... FOR UPDATE`;
3. constant-time сравнивает SHA-256;
4. проверяет unused/unrevoked state, subject, Admin activity и сохранённый
   `auth_version`;
5. помечает старую строку использованной;
6. выпускает следующую пару в той же family.

Если предъявлена использованная или отозванная строка, вся family отзывается.
Ошибка поднимается только после выхода из `session.begin()`, чтобы `401` не
откатил защитный revoke. Строчная блокировка гарантирует, что два параллельных
refresh не создадут две действующие ветки.

### Logout и credential changes

`POST /admin/auth/logout` отзывает family предъявленного refresh и удаляет
cookie; отсутствие или мусорный токен — безопасный повторяемый no-op.

Reset password увеличивает `auth_version` и отзывает все refresh-сессии Admin.
Деактивация делает то же для refresh и запрещает self-deactivation. Изменения
множества активных Admin сериализуются общим advisory lock, поэтому встречные
деактивации не оставят систему без активного аккаунта.

## HTTP-контракт

Публичные endpoints:

- `POST /admin/auth/login`;
- `POST /admin/auth/refresh`;
- `POST /admin/auth/logout`.

Endpoints с `CurrentAdmin`:

- `GET /admin/admins/me`;
- `POST /admin/admins`;
- `GET /admin/admins`;
- `GET /admin/admins/{admin_id}`;
- `PATCH /admin/admins/{admin_id}`;
- `POST /admin/admins/{admin_id}/activate`;
- `POST /admin/admins/{admin_id}/deactivate`;
- `POST /admin/admins/{admin_id}/reset-password`.

Ошибки выходят как RFC 9457 через `AppError`. Response schemas никогда не
содержат `hashed_password`, refresh hash или `auth_version`.

## Cookie и CSRF boundary

Refresh cookie имеет `HttpOnly`, path `/admin/auth`, настраиваемые `Secure` и
`SameSite`; production запрещает `Secure=false`. Default `SameSite=strict`
защищает same-site admin UI от обычного cross-site request.

Не включай `SameSite=none` только ради cross-site frontend. Текущая валидация
требует для него TLS, но полноценный cross-site режим также требует отдельного
CSRF-механизма и точной CORS policy — их этот модуль пока не реализует.

## Bootstrap первого Admin

API lifespan берёт transaction-scoped PostgreSQL advisory lock и проверяет
таблицу `admins` внутри той же транзакции:

- непустая таблица — no-op, bootstrap credentials больше не нужны;
- пустая таблица — обязательны валидные username и пароль 12–128 символов;
- несколько API replicas создают ровно одну строку;
- отсутствие credentials при пустой таблице роняет startup безопасной ошибкой;
- worker bootstrap не запускает.

Настройки:

```env
ADMIN_BOOTSTRAP_USERNAME=
ADMIN_BOOTSTRAP_PASSWORD=
ADMIN_BOOTSTRAP_TELEGRAM_ID=
ADMIN_REFRESH_COOKIE_NAME=admin_refresh
ADMIN_REFRESH_COOKIE_SECURE=false
ADMIN_REFRESH_COOKIE_SAMESITE=strict
ADMIN_REFRESH_CLEANUP_CRON=17 4 * * *
```

После первого успешного запуска bootstrap password нужно удалить из secret
store/.env. Compose передаёт `infra/.env` контейнеру через `env_file`.

## Retention и известные внешние меры

Периодическая TaskIQ-задача удаляет refresh rows только после `expires_at`.
Она зарегистрирована через `Module.tasks` и выполняется worker'ом.

Модуль не реализует rate limiting login. Перед публикацией admin API в
интернет ограничение попыток должно обеспечиваться ingress/API gateway либо
отдельным согласованным механизмом с распределённым состоянием. Не добавляй
локальный in-memory limiter: он обходится несколькими uvicorn replicas и
теряет состояние при рестарте.

## Проверяемые сценарии

Основные тесты — `tests/test_admin.py` и `tests/test_authentication.py`. При
изменении механизма сохраняй проверки:

- одинакового `401` и dummy verify;
- rehash и отсутствия plaintext secrets;
- missing/disabled/version-mismatched Admin;
- rotation, reuse family revoke и concurrent refresh;
- password/deactivation invalidation;
- self-lockout и встречной деактивации;
- concurrent bootstrap, no-op и missing credentials;
- cookie flags, no-store и production policy;
- keyset index, migration и cleanup.
