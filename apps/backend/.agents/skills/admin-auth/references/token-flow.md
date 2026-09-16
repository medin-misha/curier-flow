# Аккаунты и токены

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

## Cookie и CSRF boundary

Refresh cookie имеет `HttpOnly`, path `/admin/auth`, настраиваемые `Secure` и
`SameSite`; production запрещает `Secure=false`. Default `SameSite=strict`
защищает same-site admin UI от обычного cross-site request.

Не включай `SameSite=none` только ради cross-site frontend. Текущая валидация
требует для него TLS, но полноценный cross-site режим также требует отдельного
CSRF-механизма и точной CORS policy — их этот модуль пока не реализует.
