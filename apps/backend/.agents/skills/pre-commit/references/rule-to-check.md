# Правило → проверка

Справочник в обе стороны: каким тестом сторожится правило и что именно
утверждает упавший тест.

## Сводка по всем правилам проекта

| Правило | Проверка |
| --- | --- |
| Слои `api → modules → platform → kernel` | `uv run lint-imports` |
| Модули не импортируют друг друга | `uv run lint-imports` |
| `kernel` не знает про fastapi/starlette | `tests/test_kernel_isolation.py` |
| Процесс uvicorn не знает про `platform` | `tests/test_process_isolation.py` |
| Раскладка пакетов не разъехалась | `tests/test_project_layout.py` |
| Каждый модуль в `MODULES`, и наоборот | `tests/test_registry.py`, `tests/test_architecture.py` |
| У каждого модуля есть `AGENTS.md` | `tests/test_architecture.py::test_every_module_carries_agent_instructions` |
| `handlers.py` не импортирует `CRUD` | `tests/test_architecture.py::test_handlers_never_import_crud` |
| `services.py` не знает про HTTP | `tests/test_architecture.py::test_services_never_raise_http_exceptions` |
| Бизнес-код не вызывает `commit()` | `tests/test_architecture.py::test_modules_never_commit_the_session` |
| Пишущая зависимость закрывается до ответа | `tests/test_architecture.py::test_uow_dependencies_close_before_the_response`, `tests/test_commit_before_response.py` |
| `HTTPException` не используется | `make check` (ruff `banned-api`) |
| Наивный UTC не используется | `make check` (ruff `banned-api`) |
| Конфигурация читается только через pydantic-settings | `make check` (ruff `banned-api` на `os.getenv`/`os.environ`) |
| Все ошибки — problem+json | `tests/test_api_errors.py` |
| Keyset-пагинация работает и на дубликатах меток | `tests/test_pagination.py`, `tests/test_list_page.py` |
| Событие и данные в одной транзакции | `tests/test_storage.py::test_confirmation_and_the_event_share_one_transaction` |
| Релей не теряет и не дублирует события | `tests/test_outbox.py` |
| Повторная доставка безвредна | `tests/test_idempotency.py`, `tests/test_domain_events.py` |
| `Idempotency-Key` защищает запись | `tests/test_http_idempotency.py` |
| Модели совпадают с миграциями | `uv run alembic check` |
| Изменённая миграция откатывается | `uv run alembic downgrade -1 && uv run alembic upgrade head` на отдельной локальной базе |
| Покрытие `app.kernel` не ниже 85% | `make test` |
| Типы, формат, докстринги ядра | `make check` |
| Внешний I/O вне транзакции (новый модуль) | ревью + сторож в тестах модуля |
| Выбор `emit()` против `after_commit` | ревью |
| Keyset-индекс у новой пагинируемой таблицы | ревью + скиллы `new-module`, `db-migration` |
| Полнота `.env.example` для новых настроек | ревью + скилл `new-module` |
| Одна зона ответственности, отсутствие абстракций «на будущее» | ревью |

## Идемпотентность и порядок коммита — поимённо

```bash
uv run pytest tests/test_http_idempotency.py -v      # ключи HTTP (нужен docker)
uv run pytest tests/test_commit_before_response.py -v # коммит раньше ответа (docker)
uv run pytest tests/test_idempotency.py -v           # отметки сообщений
uv run pytest tests/test_security.py -v              # пароли и JWT
make -C ../../infra migrate && uv run alembic check
```

| Утверждение | Тест |
| --- | --- |
| Два одинаковых POST с одним ключом создают одну сущность, второй ответ идентичен первому | `test_the_same_key_and_body_return_the_stored_response` |
| Тот же ключ с другим телом — 409 | `test_the_same_key_with_a_different_body_is_a_conflict` |
| Откат уносит ключ вместе с данными | `test_the_key_row_is_committed_with_the_data` |
| Запрос, чей коммит упал, получает 500, а не 2xx | `test_a_failed_commit_is_not_answered_with_success` |
| Упавший коммит не оставляет занятый ключ | `test_a_failed_commit_leaves_no_key_reserved` |
| Область транзакции не снята при правке | `test_the_write_transaction_closes_before_the_response_is_sent` |
| Область не снята и в бизнес-модуле | `test_uow_dependencies_close_before_the_response` |
| Параллельный повтор не создаёт вторую сущность | `test_a_parallel_repeat_is_rejected_while_the_first_request_runs` |
| Ошибка освобождает ключ | `test_a_failed_request_may_be_retried_with_the_same_key` |
| Непомеченные ручки не трогаются | `test_unmarked_routes_are_untouched` |
| Уборка удаляет только просроченное и переживает параллельный запуск | `test_purge_removes_expired_keys_only`, `test_purge_is_safe_to_run_twice` |

## Правила, у которых проверки нет

Эти пять существуют только в ревью — и ровно поэтому вынесены в чек-лист
скилла `pre-commit` отдельным шагом:

| Правило | Почему автоматики нет |
| --- | --- |
| Внешний I/O вне транзакции в новом модуле | сторож из `test_storage.py` знает про `ObjectStorage`; какой клиент заведёт следующий модуль, заранее неизвестно |
| `emit()` против `after_commit` | «потерю переживём» — утверждение о бизнесе, из кода не выводится |
| Keyset-индекс у новой таблицы | «эту таблицу листают» из схемы не видно: `CRUD.list_page` вызывается в сервисе, а не объявляется на модели |
| Полнота `.env.example` | сверка «каждое поле каждого Settings-класса упомянуто» написана поимённо и только для существующих классов |
| Одна зона ответственности, абстракция только при двух реализациях | правила про смысл, а не про синтаксис; линтера для них не существует |
