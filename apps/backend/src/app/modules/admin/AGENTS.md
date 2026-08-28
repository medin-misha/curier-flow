# Admin module

Перед работой прочитай корневой `AGENTS.md` и `apps/backend/AGENTS.md`:
локальный файл дополняет их, но не рассчитывай на автоматическое объединение.

Модуль владеет администраторами, refresh-токенами и HTTP-префиксом `/admin`.
Криптографические примитивы остаются в `app.kernel.security`; наружу никогда
не выходят `hashed_password`, plaintext refresh-токен или bootstrap password.

Критичные инварианты:

- refresh одноразовый: ротация блокирует строку, reuse отзывает всё семейство;
- первый Admin создаётся lifespan из `.env` только при пустой таблице и под
  PostgreSQL advisory lock;
- публичность задаётся отсутствием `@authenticated`, а административные
  операции дополнительно проверяют живого Admin и `auth_version` в БД.

Admin объявляет локальную Pydantic-проекцию `courier.registered`, не импортируя
класс события или модели `courier_module`. Подписчик снимает snapshot только
active Admin с non-null `telegram_id` и в той же транзакции создаёт через
outbox по одному точному пяти-полевому событию
`courier.registration.telegram_notification.created` на каждую платформу.
Манифест заранее объявляет durable `telegram.notifications` с retry/DLQ, но
backend consumer этой очереди не имеет.

Карта: `handlers.py` — HTTP/cookie, `services/` — accounts/auth/bootstrap и
notification fan-out, `events.py`/`subscribers.py` — локальные событийные
контракты и их обработка, `models/` и `schemas/` — DB/API-контракты,
`tasks.py` — retention, `module.py` — регистрация, topology и startup
bootstrap. Перед изменением используй
backend skill `admin-auth`; living contract механизма находится в его
`references/mechanism.md`.

Проверка из `apps/backend`:

```bash
uv run ruff format src/app/modules/admin tests/test_admin.py
make check
make test
uv run alembic check
```
