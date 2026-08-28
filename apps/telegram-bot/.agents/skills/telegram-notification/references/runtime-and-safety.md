# Runtime and safety

## Startup

`TELEGRAM_BOT_TOKEN` обязателен, непуст и хранится как `SecretStr`; рабочего
default нет. HTTP client сначала вызывает `getMe`. Только успешный HTTP 200 с
`ok=true` разрешает открыть robust RabbitMQ connection, пассивно дождаться
topology и начать consume. Любая ошибка `getMe`, включая `401`, network и `5xx`,
завершает startup до подключения к RabbitMQ, поэтому queued deliveries не
подтверждаются и не отклоняются.

RabbitMQ connection получает `fail_fast=0` и переподключается robust-механизмом.
SIGINT/SIGTERM может прервать ожидание connection или отсутствующей topology.

## Graceful shutdown

SIGINT и SIGTERM выставляют общий stop event. После старта consumer остановка
идёт в таком порядке:

1. Отменить consume, чтобы не принимать новые deliveries.
2. Ждать завершения in-flight не дольше `TELEGRAM_SHUTDOWN_TIMEOUT` (default 30
   секунд, значение строго положительное).
3. При timeout записать только технические counts, отменить in-flight tasks и
   закрыть channel; неподтверждённая delivery вернётся в очередь.
4. Закрыть robust RabbitMQ connection, затем HTTP client.

Runtime `401`, retry publish failure, ACK failure и иное неожиданное исключение
обработчика помечают consumer fatal. Worker выполняет тот же shutdown, затем
завершается с ошибкой; текущая delivery не получает неявный ACK или reject.

## Plain-text rendering

Formatter возвращает ровно четыре строки:

```text
Новая регистрация курьера
Имя: <full_name>
Контакт: <contact_platform> — <contact>
Платформа: <display platform>
```

Display mapping: `bolt_food` -> `Bolt Food`, `foodora` -> `Foodora`, `wolt` ->
`Wolt`. Если хотя бы одно из `contact_platform`/`contact` равно `null`, третья
строка становится `Контакт: не указан`.

`sendMessage` получает только `chat_id`, `text` и
`link_preview_options={"is_disabled": true}`. `parse_mode` отсутствует, поэтому
пользовательские Markdown/HTML-последовательности остаются буквальным plain
text; preview ссылок отключён.

## Логи и ошибки

В логи, repr ошибок и process output запрещено включать token, Bot API URL с
token, `telegram_id`, имя, contact-поля, body/полный payload, отрендеренный
текст и сырой Telegram response. Произвольный невалидный `message_id` также не
логируется: допустим только нормализованный UUID.

Допустимы технические поля: нормализованный `message_id`, topic, retry attempt,
HTTP status, класс ошибки, duration/delay, queue/prefetch, in-flight count и
shutdown timeout. Приложение не пишет исходный текст transport exception и не
сохраняет его как exception cause, потому что URL может содержать token.
`httpx`, `httpcore`, `aio_pika` и `aiormq` принудительно остаются на WARNING
даже при application DEBUG, чтобы dependency logs не раскрыли URL или AMQP
body. Ошибка загрузки settings выводит только класс исключения.
