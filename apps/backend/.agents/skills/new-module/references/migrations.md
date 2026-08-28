## Шаг 12. Миграция

Полный порядок работы со схемой, включая переименования и проверку отката, —
скилл `db-migration`. Ниже — тот же порядок в объёме, нужном новому модулю.

Autogenerate ходит в базу, поэтому Postgres должен быть поднят и накатан.
Окружение стека и применение существующей цепочки принадлежат `infra/`, а
генерация новой ревизии выполняется с хоста. `DATABASE_DSN` хостового окружения
должен указывать на поднятый Postgres из `infra/`:

```bash
make -C ../../infra up-infra # запуск контейнеров всегда идёт через infra/
make -C ../../infra migrate
make revision m="add notes"
```

**Сразу отформатируй сгенерированный файл** — autogenerate пишет в своём стиле
(одинарные кавычки, длинные строки), и `make check` на нём падает:

```bash
uv run ruff format alembic/versions/<новый файл>.py
```

Затем **прочитай сгенерированный файл**:

- имя таблицы, типы колонок и nullable — те, что задумывались;
- keyset-индекс на месте и **направление сортировки сохранено**:
  ```python
  op.create_index(
      "ix_notes_keyset",
      "notes",
      [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
      unique=False,
  )
  ```
  Индекс без `DESC` бесполезен для `ORDER BY created_at DESC, id DESC`;
- переименование колонки autogenerate не распознаёт и превращает в
  «удалить + создать» — с потерей данных. Такие правки пишутся руками;
- `downgrade()` действительно возвращает базу к прежнему состоянию; проверь
  новую ревизию локальным циклом отката и повторного наката.

Проверь и накати:

```bash
make -C ../../infra migrate
uv run alembic check    # «No new upgrade operations detected»
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic check
```

Цикл отката выполняй на отдельной локальной базе без ценных данных.

`alembic check` не пустая формальность: он ловит расхождение моделей и
миграций, из-за которого `make test` упал бы на создании схемы.
