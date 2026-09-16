---
name: background-effect
description: Выбрать и подключить backend-эффект — outbox, after_commit, TaskIQ или RabbitMQ consumer. Для событий, уведомлений и фоновых задач.
---

# Побочный эффект

Рабочий каталог — `apps/backend/`. Выбери механизм, затем читай только его
правила (пути ниже относительно этого SKILL.md):

| Требование | Механизм и контекст |
| --- | --- |
| Входящее сообщение чужого сервиса | RabbitMQ consumer: [worker](../../rules/background-work.md) и [подключение](references/worker.md) |
| Надёжный эффект после изменения данных | `emit(session, Event(...))`: [события](../../rules/events.md) |
| Расписание или отложенная наша работа | TaskIQ: [worker](../../rules/background-work.md) и [подключение](references/worker.md) |
| Допустима потеря эффекта после коммита | `after_commit`: [события](../../rules/events.md) |

Для надёжного эффекта после записи используется outbox, а не прямая постановка
задачи в брокер. Изменяются запись или внешний I/O — дополнительно читай
[транзакции](../../rules/transactions.md). Не загружай правила других механизмов.

## Подключение

- Событие объявляй в `events.py` владельца; `emit()` вызывай из services.
  Поля JSON-сериализуемы; PATCH/DELETE требуют события только при наличии
  внешнего потребителя.
- Подписчик: `@subscribe(Event)`, сигнатура `(event, session)`; регистрация
  в `Module.subscribers`. Неиспользуемая сессия — `_session`.
- TaskIQ: `@schedule(...)`, регистрация в `Module.tasks`.
- Consumer: `Module.consumers` и `Module.topology`.
- Для `after_commit` регистрация в манифесте не нужна.

Проверь идемпотентность повторной доставки и атомарность данных/outbox.
Новая настройка расписания добавляется в `.env.example`. Перед коммитом —
`pre-commit`; повторно читать уже загруженные правила не нужно.
