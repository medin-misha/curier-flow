# Admin module

Модуль владеет администраторами, refresh-токенами и HTTP-префиксом `/admin`.
Криптографические примитивы остаются в `app.kernel.security`; наружу никогда
не выходят `hashed_password`, plaintext refresh-токен или bootstrap password.

Критичные инварианты:

- refresh одноразовый: ротация блокирует строку, reuse отзывает всё семейство;
- первый Admin создаётся lifespan из `.env` только при пустой таблице и под
  PostgreSQL advisory lock;
- публичность задаётся отсутствием `@authenticated`, а административные
  операции дополнительно проверяют живого Admin и `auth_version` в БД.

Карта: `handlers.py` — HTTP/cookie, `services/` — accounts/auth/bootstrap,
`models/` и `schemas/` — DB/API-контракты, `tasks.py` — retention,
`module.py` — регистрация и startup bootstrap. Перед изменением используй
backend skill `admin-auth`; living contract механизма находится в его
`references/mechanism.md`. `docs/admin_auth_plan.md` хранит план и журнал
исходной реализации, а не актуальные инструкции по развитию.

Проверка из `apps/backend`:

```bash
uv run ruff format src/app/modules/admin tests/test_admin.py
make check
make test
uv run alembic check
```
