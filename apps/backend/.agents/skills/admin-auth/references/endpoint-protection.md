# Защита HTTP-ручек

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
Для ручки, одновременно помеченной `@idempotent`, эта JWT-проверка выполняется
до поиска replay-ответа: сохранённый ответ не превращает endpoint в публичный.

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

## HTTP-контракт

Публичные endpoints:

- `POST /admin/auth/login`;
- `POST /admin/auth/refresh`;
- `POST /admin/auth/logout`;
- `POST /courier`.

Courier endpoints с `@authenticated`:

- `GET /courier`;
- `POST /courier/bulk-delete`;
- `PATCH /courier/bulk-status`;
- `GET /courier/{courier_id}`;
- `PATCH /courier/{courier_id}`;
- `DELETE /courier/{courier_id}`;
- `POST /courier/{courier_id}/platform-accounts`;
- `PATCH /courier/{courier_id}/platform-accounts/{account_id}`;
- `POST /courier/{courier_id}/documents`;
- `PATCH /courier/{courier_id}/documents/{document_id}`;
- `DELETE /courier/{courier_id}/documents/{document_id}`.

Обе массовые операции Courier дополнительно требуют `Idempotency-Key`;
JWT проверяется и при воспроизведении сохранённого ответа.

Все endpoints `/transport` используют `@authenticated`: CRUD транспорта и
комплектации, чтение истории аренды, создание/завершение аренды и прикрепление
договора. Создающие и командные POST дополнительно требуют `Idempotency-Key`.

Все CRUD endpoints `/receipts` и `/receipts/tags` используют `@authenticated`;
создание чека и тега дополнительно требует `Idempotency-Key`.

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
