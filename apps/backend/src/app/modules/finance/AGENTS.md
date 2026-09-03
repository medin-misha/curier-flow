# Модуль `finance`

Перед работой прочитай корневой `AGENTS.md` и `apps/backend/AGENTS.md`: этот
файл дополняет их, но не объединяется с ними автоматически.

Модуль владеет чеками компании, справочником тегов расходов и HTTP-ресурсом
`/receipts`. Статистика и
агрегации не входят в backend-контракт: их строит frontend из CRUD-данных по
календарному полю `Receipt.date`, а не по аудиторскому `created_at`.

Критичные инварианты:

- каждый чек ссылается на отдельный `ready` File из общего platform-каталога;
- чек может ссылаться не более чем на один необязательный ReceiptTag;
- удаление ReceiptTag снимает его со всех связанных чеков;
- связанный File нельзя перевести в `deleting`, пока чек не удалён или не
  переведён на другой файл;
- все ручки защищены `@authenticated`, а создание также использует
  `@idempotent`;
- список использует keyset `(created_at DESC, id DESC)`.

Карта: `handlers.py` содержит только HTTP, `services.py` — CRUD и правила File,
`models/` — ORM/DB-инварианты, `schemas/` — публичный контракт, `module.py` —
манифест. Проверка из `apps/backend/`:

```bash
uv run ruff format src/app/modules/finance tests/test_finance.py
make check
make test
uv run alembic check
```
