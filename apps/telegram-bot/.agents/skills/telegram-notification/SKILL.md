---
name: telegram-notification
description: Изменить Telegram notification worker с сохранением его payload, AMQP, delivery, Bot API, lifecycle и logging contract. Применяй для apps/telegram-bot; не применяй для backend fan-out или infra wiring.
---

# Telegram notification

Это канонический service workflow и living contract для
`apps/telegram-bot/`. Сервис остаётся sending-only, не импортирует backend и не
получает polling, webhook, HTTP server или собственную БД.

## Маршрутизация контекста

- Payload, AMQP envelope, topology или retry metadata:
  [AMQP contract](references/amqp-contract.md).
- ACK/retry/DLQ, Telegram errors и at-least-once:
  [delivery semantics](references/delivery-semantics.md).
- Startup/shutdown, `getMe`, rendering и безопасные логи:
  [runtime and safety](references/runtime-and-safety.md).

## Workflow

1. Работай из `apps/telegram-bot/` и выбери только относящиеся к изменению
   references. Для изменения межсервисного envelope прочитай все три.
2. Сверь затронутый контракт с `src/telegram_bot/` и его тестами. Backend Admin
   events/module/outbox используй только как внешнее доказательство producer
   boundary, а не как Python-зависимость или источник внутреннего дизайна.
3. Сохрани строгую валидацию без compatibility parsing. Breaking change тела,
   типа или смысла поля требует нового routing key и согласованного изменения
   producer/consumer.
4. Зафиксируй изменение тестом на наблюдаемую delivery/lifecycle semantics.
   Bot API проверяй только локальным stub; настоящий token и внешняя сеть в
   тестах запрещены.
5. Если реализация и этот living contract расходятся, установи поведение по
   коду и тестам и обнови reference в том же изменении.

## Проверка

```bash
make check
make test
../../scripts/check-agent-context.sh
```
