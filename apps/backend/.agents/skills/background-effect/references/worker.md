# Подключение фоновой работы

## TaskIQ

Используй `@schedule(cron=...)` или `@schedule(interval=...)`; расписание бери
из Settings модуля. Пример обоих вариантов —
`src/app/modules/storage/tasks.py` (пути от `apps/backend/`).

- Фабрика сессий читается через `db_session.session_factory`, а не импортом
  по имени: тесты подменяют глобаль ядра.
- При пакетной обработке ошибка одного элемента логируется и не прекращает
  обработку остальных.
- Внешние клиенты создаёт задача: lifespan модуля работает только в API.
- Корутина в `Module.tasks` без `@schedule` роняет startup.

## RabbitMQ consumer

`consumers.py` сохраняет внешний формат сообщения; он не меняется локально.
В `module.py` добавь `TopologyDecl` и `ConsumerDecl`.
Значения `dead_letter`, `retry_ttl_ms`, `prefetch`, `requires_idempotency`
сверяй с `src/app/kernel/registry.py`.

Повторная доставка защищена `run_once` из `src/app/platform/idempotency.py`:
отметка `processed_messages` и эффект фиксируются одной транзакцией.
