# Telegram notification worker

Самостоятельный Python 3.12 service, который читает регистрации Courier из
RabbitMQ и отправляет plain-text уведомления через Telegram Bot API. Service
только отправляет сообщения: polling, webhook, команды `/start`, БД и импорты
из `apps/backend` отсутствуют.

## Контракт

- queue: `telegram.notifications`;
- routing key: `courier.registration.telegram_notification.created`;
- payload: `telegram_id`, `full_name`, nullable `contact_platform`/`contact`,
  `platform` (`bolt_food`, `foodora`, `wolt`);
- `content_type`: `application/json`, `message_id`: UUID backend outbox;
- prefetch: `1`, retry delay: 30 секунд.

Topology создаёт backend. Worker только пассивно проверяет main queue, retry и
DLQ вместе с их durable/TTL/DLX параметрами. Несовпадение — ошибка
конфигурации, а отсутствие topology ожидается до запуска backend worker.

## Локальный запуск

Нужны Python 3.12, `uv`, доступные RabbitMQ и Bot API. Создайте локальный файл:

```bash
cp .env.example .env
```

Задайте `TELEGRAM_BOT_TOKEN`, затем выполните:

```bash
make install
make run
```

Bot API не может первым начать личный диалог: каждый Admin должен заранее
открыть бота и нажать `/start`. Если чат не существует или бот заблокирован,
Telegram 400/403 диагностируется как permanent failure и сообщение уходит в
`telegram.notifications.dlq`.

## Проверки

```bash
make check
make test
```

Тесты используют локальный stub Telegram API и не требуют настоящего token или
внешней сети. Container image собирается и проверяется только через `infra/`.

## Delivery semantics

- успешный `sendMessage` подтверждается ACK;
- invalid message и permanent 4xx отклоняются в DLQ;
- network, 429 и 5xx подтверждённо публикуются в retry перед ACK;
- 401 останавливает consumer, оставляя delivery unacked;
- SIGTERM отменяет consume, ждёт in-flight до
  `TELEGRAM_SHUTDOWN_TIMEOUT`, затем закрывает HTTP/RabbitMQ clients.

Гарантия — at-least-once. Если Telegram принял сообщение, а процесс завершился
до ACK, повторная доставка и дубликат Telegram-сообщения допустимы.

## Безопасность

Token хранится как `SecretStr`, не имеет default и не попадает в image.
Структурные логи не содержат token, `telegram_id`, имени, контакта, полного
payload, отрендеренного текста или сырого Telegram response. RabbitMQ
management и DLQ всё равно содержат PII, поэтому production vhost/user и доступ
к management UI должны быть ограничены.
