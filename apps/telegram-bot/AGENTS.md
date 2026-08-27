# Telegram Bot

Самостоятельный Python 3.12 worker для исходящих Telegram-уведомлений. Рабочий
каталог сервиса — `apps/telegram-bot/`; код backend не является его Python-
зависимостью.

## Рабочий контекст

- Запускай service-scoped сессию командой `codex --cd apps/telegram-bot`.
- Для изменения queue contract, consumer, formatter или Telegram-клиента
  обязательно используй skill `telegram-notification`.
- Источник контракта до появления отдельной документации сервиса — разделы
  6.2, 6.3, 8 и 10 файла `../../notification_spec.md`.
- Сейчас в сервисе создан только контекстный bootstrap. При добавлении runtime-
  кода одновременно зафиксируй реальные команды установки и проверок в этом
  файле; не придумывай команды до появления `Makefile` и `pyproject.toml`.

## Неподвижные границы

- Сервис только отправляет сообщения: polling/webhook входящих Telegram updates
  и привязка Admin через `/start` в MVP не входят.
- Topology создаёт backend. Bot пассивно проверяет точную очередь
  `telegram.notifications` и не объявляет AMQP-сущности с другими аргументами.
- Доставка at-least-once: ACK/retry/DLQ и graceful shutdown должны сохранять
  правила skill `telegram-notification`.
- Token, `telegram_id`, имя, контакт и полный payload запрещено писать в логи.

## Runtime и команды

Service использует Python 3.12 и `uv`; реальные команды определены в
`pyproject.toml` и `Makefile`:

```bash
make install
make check
make test
make run
```

`make check` сам запускает `../../scripts/check-agent-context.sh`. Container
image собирается и проверяется только из `infra/`.

## Queue contract

- queue: `telegram.notifications`;
- routing key: `courier.registration.telegram_notification.created`;
- payload содержит ровно `telegram_id`, `full_name`, nullable
  `contact_platform`, nullable `contact`, `platform`;
- prefetch равен `1`, `message_id` — обязательный UUID backend outbox;
- topology создаёт backend, bot проверяет её только пассивно;
- ACK разрешён после успешного Telegram side effect либо после publisher
  confirm retry copy; invalid/permanent delivery отклоняется в DLQ;
- 401 оставляет delivery unacked и останавливает процесс;
- SIGTERM сначала отменяет consume, затем ограниченно ждёт in-flight.

Тесты используют локальный stub Bot API. Настоящий token и внешняя сеть в
тестах запрещены.
