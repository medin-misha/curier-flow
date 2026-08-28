# Telegram Bot

Готовый самостоятельный worker для исходящих Telegram-уведомлений. Рабочий
каталог сервиса — `apps/telegram-bot/`; код backend не является его Python-
зависимостью.

## Рабочий контекст

- Перед задачей прочитай корневой `../../AGENTS.md`: локальный файл дополняет
  общие правила, но не рассчитывай на их автоматическое объединение.
- Для задач сервиса используй `apps/telegram-bot/` как рабочий каталог, чтобы
  применялись локальные инструкции и project skills.
- Для изменения queue contract, consumer, formatter или Telegram-клиента
  обязательно используй skill `telegram-notification`: это канонический living
  contract для payload, AMQP, delivery, lifecycle, rendering и логов.
- Фактическое поведение сверяй с `src/telegram_bot/`, `tests/`, `Makefile`,
  `pyproject.toml` и `Dockerfile`.
- Реализованный runtime проверяет token через `getMe`, подключается к RabbitMQ,
  пассивно ждёт topology backend и отправляет уведомления через `sendMessage`.

## Неподвижные границы

- Сервис только отправляет сообщения: polling/webhook входящих Telegram updates
  и привязка Admin через `/start` в MVP не входят.
- Topology создаёт backend. Bot пассивно проверяет точную очередь
  `telegram.notifications` и не объявляет AMQP-сущности с другими аргументами.
- Доставка at-least-once: ACK/retry/DLQ и graceful shutdown должны сохранять
  правила skill `telegram-notification`.
- Token, `telegram_id`, имя, контакт и полный payload запрещено писать в логи.

## Runtime и команды

Container использует Python 3.12; `pyproject.toml` поддерживает Python
`>=3.12,<3.14`, зависимости зафиксированы `uv.lock`. Из каталога сервиса
доступны команды:

```bash
make install
make check
make test
make run
```

Прямой `make run` требует непустой `TELEGRAM_BOT_TOKEN`. Только стек через
`infra/` считает worker опциональным и включает его Compose profile при
непустом token.

`make check` проверяет agent context, lockfile, формат, lint и типы; `make test`
запускает unit- и stub-integration тесты с покрытием. Тесты используют локальный
stub Bot API: настоящий token и внешняя сеть запрещены.

Контейнерами управляй только через `infra/`. Из корня репозитория сначала
прочитай `make -C infra help`: `up` поднимает инфраструктуру, применяет миграции
и запускает приложения, а `reboot-apps` пересобирает и пересоздаёт приложения.
При пустом `TELEGRAM_BOT_TOKEN` цели `up` и `up-apps` предупреждают и пропускают
Telegram profile; при непустом token собирают и запускают worker. `make -C
infra check` проверяет Compose-конфигурацию и agent context, но не собирает
image.

## Канонический контракт

Детальные payload/AMQP значения, матрица ACK/retry/DLQ, Bot API classification,
startup/shutdown, plain-text rendering и logging policy находятся только в
skill `telegram-notification` и его `references/`. Считай их living contract
сервиса и обновляй вместе с соответствующим кодом и тестами; README остаётся
операционным обзором, а backend — только внешним producer boundary.
