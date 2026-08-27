# Courier module

Модуль владеет aggregate `Courier -> platform_accounts/documents -> File` и
HTTP-префиксом `/courier`. ORM `File`, S3 primitives и физическая очистка
остаются в `app.platform.files`/storage; импортировать `app.modules.storage`
запрещено.

Критичные инварианты:

- aggregate upload всегда идёт как `staging commit -> S3 без DB-транзакции ->
  короткая final transaction`; успешная final transaction одновременно
  создаёт ready File, Document и `FileConfirmed` outbox;
- Document исчезает из aggregate с момента `File.status=deleting`; физический
  S3/File cleanup выполняет универсальная storage-задача;
- natural keys POST — нормализованные email/phone. Повтор возвращает
  сохранённый aggregate и не дополняет его входным payload.
- только winner-ветка финальной транзакции aggregate POST записывает
  `CourierRegistered` (`courier.registered`) в outbox после фактического
  INSERT Courier; natural-key repeat, concurrent loser и nested account POST
  событие не создают.

Карта: `handlers.py` разбирает HTTP/multipart, пакет `services/` содержит
разделённые по ответственности aggregate, upload и retention-сервисы, а его
`__init__.py` задаёт публичный фасад. `models/`/`schemas/` задают контракт,
`tasks.py` подключает retention, `module.py` — единственная
регистрация/lifespan.

Перед изменением используй локальный skill
`.agents/skills/courier-module/SKILL.md`. Проверка из `apps/backend`:

```bash
uv run ruff format src/app/modules/courier_module tests/test_courier_module.py
make check
make test
uv run alembic check
```
