---
name: telegram-notification
description: Реализовать или изменить consumer, queue contract, formatter и Telegram Bot API client сервиса apps/telegram-bot с точной AMQP-семантикой. Применяй для обработки courier.registration.telegram_notification.created, ACK/retry/DLQ, startup/shutdown, рендеринга и связанных тестов; не применяй для backend fan-out или infra wiring.
---

# Telegram notification

Рабочий каталог — `apps/telegram-bot/`. Перед изменением читай разделы 6.2,
6.3, 8 и 10 файла `../../notification_spec.md`: это источник межсервисного
контракта. Сервис не импортирует код из `apps/backend` и не меняет контракт на
основании внутренней модели backend.

## Границы сервиса

- Это sending-only Python 3.12 worker без polling, webhook и HTTP-порта.
- В MVP нет собственной БД и exactly-once гарантии. После принятого Telegram
  side effect возможен дубль при падении до ACK; не маскируй это обещанием
  идемпотентности по `message_id`.
- Backend владеет topology. На startup пассивно дождись её появления и считай
  несовпадение durable/DLX/retry аргументов ошибкой конфигурации.

## Точный queue contract

Принимай JSON-объект ровно с пятью полями; лишние поля и нестрогие
преобразования запрещены:

| Поле | Контракт |
| --- | --- |
| `telegram_id` | integer `> 0`, signed 64-bit |
| `full_name` | string длиной 1–255 |
| `contact_platform` | string до 32 символов или `null` |
| `contact` | string до 255 символов или `null` |
| `platform` | только `bolt_food`, `foodora` или `wolt` |

Транспортные метаданные не дублируются в body:

| Параметр | Точное значение |
| --- | --- |
| exchange / type | `domain.events` / `topic`, durable |
| routing key | `courier.registration.telegram_notification.created` |
| queue / binding | `telegram.notifications` / точный routing key, durable |
| delivery / content type | persistent / `application/json` |
| message ID | обязательный UUID строки backend outbox |
| retry delay | 30 000 ms |
| retry entities | `telegram.notifications.retry`, `telegram.notifications.retry.return` |
| DLX / DLQ | `telegram.notifications.dlx` / `telegram.notifications.dlq` |
| prefetch | `1` |

Breaking change payload, типа или смысла поля требует нового routing key. Не
добавляй совместимость, которая молча принимает другой контракт.

## ACK, retry и DLQ

| Результат обработки | Действие |
| --- | --- |
| `sendMessage` успешен | ACK |
| Невалидный JSON/schema/content type/message ID | сразу DLQ без Telegram-вызова |
| Network timeout/connect error | confirmed publish в retry, затем ACK исходного |
| Telegram 429 | учесть `parameters.retry_after`, затем retry |
| Telegram 5xx | retry |
| Telegram 400/403 для chat ID | сразу DLQ |
| Telegram 401 token error | остановить consumer/process, оставить сообщение unacked |
| исчерпан `TELEGRAM_MAX_RETRIES` | DLQ |

При retry сохраняй body, routing key, content type, `message_id` и correlation
headers, увеличивай `x-retry-attempt`. Исходное сообщение ACK только после
publisher confirm retry-copy. Для terminal DLQ используй настроенный dead-letter
маршрут без requeue; не превращай постоянную ошибку в бесконечный цикл.

Для 429 не вызывай Telegram раньше `retry_after`: если фиксированный TTL
короче, асинхронно дождись остатка. Не ACK сообщение при неуспешной публикации
retry-copy. Startup сначала проверяет token через `getMe`, затем начинает
consume; auth failure на startup не отправляет накопленные сообщения в DLQ.

На SIGTERM прекрати принимать новые сообщения, дождись in-flight не дольше
настроенного shutdown timeout и закрой HTTP/RabbitMQ clients. Оставшееся
unacked сообщение должно вернуться в очередь.

## Рендеринг и секреты

Отправляй plain text без `parse_mode` и отключай preview ссылок. Используй
display mapping `bolt_food → Bolt Food`, `foodora → Foodora`, `wolt → Wolt`;
если `contact_platform` или `contact` отсутствует, выводи
`Контакт: не указан`.

Храни bot token как `SecretStr`; у него нет рабочего default. Никогда не пиши
в логи token, `telegram_id`, `full_name`, `contact`, отрендеренный текст, весь
payload или сырой Telegram response с пользовательскими данными. Допустимы
`message_id`, topic, attempt, HTTP status, класс ошибки и длительность.

## Проверка изменения

Тестами зафиксируй строгий payload и enum, plain-text/null rendering, отсутствие
секретов и PII в repr/логах, `getMe` до consume и всю матрицу ACK/retry/DLQ.
Отдельно проверь publisher confirm до ACK, сохранение `message_id`, retry limit,
429 delay, SIGTERM с in-flight и redelivery после падения до ACK. Используй
локальный stub HTTP server, а не настоящий Telegram API.
