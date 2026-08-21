## Шаг 15. Проверка

Форматируется **только своё**: `ruff format .` прошёлся бы по всему
репозиторию и внёс правки в файлы, о которых никто не просил.

```bash
uv run ruff format src/app/modules/<name> tests/test_<name>.py \
    src/app/modules/__init__.py alembic/versions/<новый файл>.py
make check   # формат, линтер, типы, правила зависимостей
make test    # весь прогон, включая архитектурные тесты (нужен Docker)
```

Оба обязаны быть зелёными **без правок за пределами каталога модуля**.

`make test`, а не `pytest tests/test_<name>.py`: тест модуля, проходящий в
одиночку, вполне может падать в полном прогоне из-за строк, оставленных
соседями.

Перед коммитом пройди скилл `pre-commit`: кроме этих двух команд он проверяет
то, чего линтер не ловит, — нужность `@idempotent`, выбор `emit()` против
`after_commit`, keyset-индекс и полноту `.env.example`.

### Живая проверка

Контейнеры `api` и `worker` запускаются только через `infra/` из образа,
собранного из кода. Стек, поднятый до появления модуля, о новых ручках не
знает и ответит на них 404. Перед живой проверкой пересобери приложения:

```bash
make -C ../../infra reboot-apps
```

Дальше — полный цикл ручками; те же команды положи в `AGENTS.md` модуля:

```bash
ID=$(curl -s localhost:8000/notes -H 'content-type: application/json' \
  -d '{"title":"first","body":"hello"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
curl -s localhost:8000/notes/$ID
curl -s "localhost:8000/notes?limit=2"                       # next_cursor не null
curl -s -X PATCH localhost:8000/notes/$ID -H 'content-type: application/json' \
  -d '{"title":"second"}'                                    # 200, updated_at сдвинулся
curl -s -X PATCH localhost:8000/notes/$ID -H 'content-type: application/json' \
  -d '{"title":null}'                                        # 422 problem+json
curl -si -X DELETE localhost:8000/notes/$ID | head -1        # 204
curl -s -X DELETE localhost:8000/notes/$ID                   # 404 problem+json
```

Если что-то красное, смотри сюда:

| Симптом | Причина |
| --- | --- |
| `test_every_module_on_disk_is_registered` | забыта запись в `MODULES` |
| `test_every_registered_module_exists_on_disk` | имя в `MODULES` не совпало с каталогом |
| `test_every_module_carries_agent_instructions` | нет `<модуль>/AGENTS.md` |
| `test_handlers_never_import_crud` | в `handlers.py` импортирован `CRUD` |
| `test_services_never_raise_http_exceptions` | в `services.py` упомянут `HTTPException` |
| `test_modules_never_commit_the_session` | где-то вызван `session.commit()` |
| `test_uow_dependencies_close_before_the_response` | `Depends(get_uow)` без `scope="function"` |
| `lint-imports`: `Business modules never import each other` | импортирован соседний модуль — в том числе его `events.py` (шаг 6) |
| `lint-imports`: `Layers` | модуль импортирует `app.api` |
| `mypy`: `Incompatible types in assignment` в схеме патча | `field: str = Field(default=None)`; правильно `field: str \| None = Field(default=None, ...)` |
| 500 и `IntegrityError` на PATCH с `null` | в схеме патча нет валидатора, отвергающего явный `null` |
| 409 `Fields are not patchable` на законное поле | поле есть в схеме патча, но забыто в `Model.__patchable__` |
| 404 на новые ручки при живой проверке | контейнер `api` собран до появления модуля: `make -C ../../infra reboot-apps` |
| тест проходит один, падает в прогоне | таблица модуля не чистится между тестами |
| `ruff format --check` на `alembic/versions/…` | миграция не отформатирована после генерации |
| `UndefinedTable` в тестах модуля | миграция не сгенерирована или не накатана |
| `alembic check` нашёл операции | модель и миграция разъехались |
| `mypy` ругается на `app.state` | нужен `cast(...)`: `app.state` не типизирован |
