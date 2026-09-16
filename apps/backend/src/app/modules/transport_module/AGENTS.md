# Transport module

Применяются [root](../../../../../../AGENTS.md) и [backend](../../../../AGENTS.md)
правила; читай их, если ещё не загружены.

Модуль владеет транспортом, его текущей комплектацией и историей аренды.
Курьер задаётся строковым FK без ORM-импорта соседнего бизнес-модуля; договор
ссылается только на `app.platform.files.File`.

Критичные инварианты:

- периоды одного транспорта и одного курьера не пересекаются; это гарантируют
  PostgreSQL exclusion constraints, а не предварительная проверка сервиса;
- подписанный договор нельзя заменить, отвязать или удалить вместе с арендой;
  он также блокирует удаление транспорта, курьера и перевод File в `deleting`;
- все HTTP endpoints точечно защищены `@authenticated`; создающие и командные
  POST дополнительно используют `@idempotent`;
- списки используют только keyset `(created_at DESC, id DESC)`, вложенные
  списки имеют parent-scoped индекс.

Карта: `handlers.py` содержит только HTTP, `services/` — запросы и
бизнес-правила, `models/` — ORM/DB-инварианты, `schemas/` — публичный контракт,
`module.py` — манифест. Проверка из `apps/backend`:

```bash
uv run ruff format src/app/modules/transport_module tests/test_transport_module.py
make check
make test
uv run alembic check
```
