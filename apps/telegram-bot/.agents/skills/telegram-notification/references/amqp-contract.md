# AMQP contract

## Topology

Backend создаёт и связывает topology до запуска consumer. Telegram worker не
создаёт и не bind'ит AMQP-сущности, а пассивно проверяет их параметры.

| Сущность | Тип и параметры | Связь |
| --- | --- | --- |
| `domain.events` | durable `topic` exchange | routing key `courier.registration.telegram_notification.created` |
| `telegram.notifications` | durable queue, `x-dead-letter-exchange=telegram.notifications.dlx` | binding к `domain.events` по точному routing key |
| `telegram.notifications.dlx` | durable `fanout` exchange | binding к `telegram.notifications.dlq` |
| `telegram.notifications.dlq` | durable queue | terminal deliveries |
| `telegram.notifications.retry` | durable `fanout` exchange | binding к одноимённой retry queue |
| `telegram.notifications.retry` | durable queue, `x-message-ttl=30000`, `x-dead-letter-exchange=telegram.notifications.retry.return` | фиксированная выдержка retry copy |
| `telegram.notifications.retry.return` | durable `fanout` exchange | binding обратно к `telegram.notifications` |

Worker пассивно объявляет все перечисленные exchanges и queues с точными
type/durable/TTL/DLX параметрами и устанавливает `prefetch_count=1`. Binding
пассивным declare не проверяется: его точное значение является producer
boundary. Отсутствующую сущность worker ждёт с интервалом 2 секунды; конфликт
параметров завершает startup как configuration error. Consume использует
manual acknowledgements (`no_ack=False`).

Рабочий канал открывается с `publisher_confirms=True` и
`on_return_raises=True`; этот же канал используется для retry publish.

## Payload

Body является JSON-объектом ровно с пятью обязательными полями. Отсутствующее
поле, лишнее поле и преобразование типа запрещены.

| Поле | Точное значение |
| --- | --- |
| `telegram_id` | JSON integer, не boolean, `> 0` и `<= 9223372036854775807` |
| `full_name` | JSON string длиной 1-255 |
| `contact_platform` | JSON string длиной до 32 включительно или `null` |
| `contact` | JSON string длиной до 255 включительно или `null` |
| `platform` | только `bolt_food`, `foodora` или `wolt` |

Пустая строка допустима для обоих contact-полей, но не для `full_name`.
Nullable-поля всё равно обязаны присутствовать. Topic и транспортные metadata
в body не дублируются.

## Envelope

Первичная публикация backend имеет routing key
`courier.registration.telegram_notification.created`, `content_type` ровно
`application/json`, persistent delivery и `message_id`, равный строковому UUID
строки outbox. Producer также ставит timestamp, переносит `request_id` и при
наличии `actor_id` в headers и ждёт publisher confirm.

Consumer до Bot API строго проверяет:

- `routing_key` равен контрактному значению;
- `content_type` равен `application/json`;
- `message_id` является непустой строкой, разбираемой как UUID;
- `x-retry-attempt` отсутствует либо является неотрицательным integer, но не
  boolean;
- body соответствует точной JSON-схеме выше.

Delivery mode и произвольные producer headers consumer не валидирует. При
retry он копирует body, content type/encoding, `message_id`, priority,
correlation ID, reply-to, timestamp, type, app ID и все headers, увеличивает
`x-retry-attempt` на один и принудительно ставит persistent delivery. Copy
публикуется mandatory в `telegram.notifications.retry`; входящий routing key
сохраняется, а при его отсутствии используется контрактный.
