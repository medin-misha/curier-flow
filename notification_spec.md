# Спецификация Telegram-уведомлений о регистрации Courier

Статус: готово к реализации

Дата аудита: 2026-08-26

Область: backend + новый `telegram-bot` service + `infra/`

## 1. Цель

После **фактического создания** нового `Courier` каждый активный администратор,
у которого сохранён `telegram_id`, должен получить Telegram-уведомление.
Backend не вызывает Telegram API из HTTP-запроса: он надёжно формирует события
через существующий transactional outbox и RabbitMQ, а отдельный сервис
`apps/telegram-bot/` читает свою очередь и вызывает Telegram Bot API.

Итоговое сообщение очереди содержит ровно бизнес-поля из требования:

```json
{
  "telegram_id": 123456789,
  "full_name": "Jan Novak",
  "contact_platform": "telegram",
  "contact": "@jan",
  "platform": "wolt"
}
```

`message_id`, `request_id`, routing key и content type являются транспортными
метаданными AMQP и не дублируются в JSON.

## 2. Что уже есть в репозитории

- `Admin.telegram_id` уже реализован как nullable, unique, positive `BIGINT`;
  create/PATCH/bootstrap и API response его поддерживают
  (`apps/backend/src/app/modules/admin/models/admin.py:20`,
  `schemas/requests.py:23`, `services/accounts.py:41`). Новая колонка и миграция
  для этой задачи не нужны.
- `Courier` уже содержит `full_name`, nullable `contact_platform` и nullable
  `contact` (`courier_module/schemas/requests.py:47`,
  `models/courier.py:47`).
- Courier создаётся сразу с 1–3 уникальными platform accounts; возможные
  значения — `bolt_food`, `foodora`, `wolt`
  (`schemas/requests.py:62`, `models/platform_account.py:17`).
- Единственная достоверная точка появления нового Courier — winner-ветка
  `_finalize_new_aggregate()`: `INSERT ... ON CONFLICT DO NOTHING` внутри
  финальной транзакции (`services/couriers.py:254`). Natural-key повтор
  возвращает существующую запись и не является новой регистрацией.
- Backend уже имеет transactional outbox, publisher confirms, durable
  RabbitMQ topology, retry/DLQ и дедупликацию входящих сообщений через
  `processed_messages` (`kernel/events/`, `platform/rabbitmq.py`, `worker.py`).
- Outbox публикует JSON в topic exchange `domain.events`; `message_id` равен UUID
  строки outbox, routing key равен topic события
  (`kernel/events/outbox.py:63`, `platform/domain_events.py:67`).
- Контейнеры запускаются только через `infra/`; инфраструктура и приложения
  используют общую внешнюю сеть `curier-flow`.
- Готового Telegram-сервиса или Telegram-клиента в репозитории нет.

## 3. Зафиксированные продуктовые решения

Эти решения делают план исполнимым без дополнительных вопросов. Если продукту
нужна другая семантика, этот раздел следует изменить **до** реализации.

1. Получатели — все строки `Admin`, для которых
   `is_active IS TRUE AND telegram_id IS NOT NULL`. Tenant/fleet/role и связь
   Courier с конкретным Admin в текущей модели отсутствуют.
2. Поле `platform` в целевом контракте остаётся в единственном числе. Поэтому
   создаётся одно queue message и одно Telegram-сообщение на каждую пару
   `Admin × CourierPlatformAccount`. Два администратора и три платформы дают
   шесть сообщений. Если нужен один Telegram на Courier, контракт надо заранее
   заменить на `platforms: list[...]`.
3. Триггер — только создание корня Courier. Последующее добавление platform
   account к существующему Courier уведомление не создаёт.
4. Natural-key повтор (`200 OK`) и проигравший конкурентный create не создают
   повторных уведомлений.
5. `contact_platform` и `contact` остаются nullable; бот выводит
   `не указан`, а не отбрасывает сообщение.
6. Список получателей снимается в момент обработки `courier.registered`
   admin-подписчиком. Нет исторического backfill: ID, привязанный позже, не
   получает старые события; ID, отвязанный до обработки, их не получает.
7. Под «прикрепил telegram_id» понимается существующий защищённый
   `PATCH /admin/admins/{admin_id}`. `/start`-link/deep-link, автоматическая
   верификация Telegram-аккаунта и изменение admin API в MVP не входят.
8. Текущая positive-проверка `telegram_id` означает только личные чаты.
   Группы/каналы с отрицательными chat IDs не поддерживаются.
9. Доставка до RabbitMQ — at-least-once. Редкий дубль Telegram-сообщения в окне
   «Telegram принял запрос, процесс умер до ACK» допустим для MVP; Telegram API
   не даёт общей атомарной транзакции с RabbitMQ.
10. Уведомление отправляется для каждого фактически созданного Courier,
    независимо от `consent_to_processing`. Перед production это решение и
    передачу контактных данных во внешний сервис Telegram должен подтвердить
    владелец privacy/compliance.

## 4. Границы MVP

Входит:

- событие фактической регистрации Courier;
- выбор активных Admin с Telegram ID;
- durable fan-out в отдельную RabbitMQ queue;
- отдельный sending-only Telegram worker;
- retry, DLQ, graceful shutdown, структурные логи;
- unit, integration и ручной smoke test.

Не входит:

- polling/webhook входящих Telegram updates и команды бота;
- автоматическая привязка Admin через `/start`;
- frontend-изменения;
- роли, tenant/fleet routing или назначение ответственного Admin;
- группы и каналы;
- повторная отправка старых регистраций после поздней привязки ID;
- строгая exactly-once доставка во внешний Telegram API.

## 5. Архитектура

Прямой запрос Admin из `courier_module` запрещён правилом независимости
business modules. Поэтому используется двухэтапная цепочка событий:

```mermaid
sequenceDiagram
    participant Site as Public site
    participant Courier as courier_module
    participant DB as PostgreSQL/outbox
    participant Worker as Backend worker
    participant Admin as admin subscriber
    participant MQ as RabbitMQ
    participant Bot as telegram-bot
    participant TG as Telegram Bot API

    Site->>Courier: POST /courier
    Courier->>DB: Courier + accounts + courier.registered
    DB-->>Site: commit, затем 201
    Worker->>MQ: relay courier.registered
    MQ->>Admin: backend domain queue
    Admin->>DB: snapshot active Admins + notification outbox fan-out
    Worker->>MQ: relay courier.registration.telegram_notification.created
    MQ->>Bot: telegram.notifications
    Bot->>TG: sendMessage(chat_id=telegram_id)
    TG-->>Bot: success
    Bot->>MQ: ACK
```

Гарантии по границам:

- Courier и `courier.registered` коммитятся вместе.
- Обработка `courier.registered`, отметка `processed_messages` и все строки
  notification outbox коммитятся вместе.
- Недоступность RabbitMQ или Telegram не откатывает создание Courier.
- Durable Telegram queue существует до первой публикации и хранит сообщения,
  пока bot service выключен.

`after_commit`, прямой `publish()`, `kiq()` или Telegram HTTP внутри
Courier/admin-транзакции запрещены. Выбор `emit()` следует локальному skill
`background-effect` и правилам `events.md`, `background-work.md`,
`transactions.md`.

## 6. Контракты событий

### 6.1. Внутренний факт `courier.registered`

Владелец: `courier_module`.

Потребитель: локальная проекция события в `admin` module.

Назначение: перенести все данные, нужные fan-out, без чтения Courier-таблиц
чужим модулем.

```json
{
  "courier_id": "0198...",
  "full_name": "Jan Novak",
  "contact_platform": "telegram",
  "contact": "@jan",
  "platforms": ["wolt", "bolt_food"]
}
```

Поля:

| Поле | Тип | Правило |
| --- | --- | --- |
| `courier_id` | UUID | ID фактически вставленного Courier; нужен для трассировки backend |
| `full_name` | string | сохранённое значение, 1–255 символов |
| `contact_platform` | string/null | сохранённое значение, максимум 32 |
| `contact` | string/null | сохранённое значение, максимум 255 |
| `platforms` | array[string] | 1–3 уникальных значения `bolt_food`, `foodora`, `wolt` |

Событие эмитится ровно один раз в winner-ветке финальной transaction, после
того как известен `courier_id`, и до выхода из `session.begin()`. Оно не
эмитится из HTTP handler и не зависит от статуса ответа.

Admin не импортирует класс из `courier_module.events`; он объявляет собственную
Pydantic-проекцию с тем же topic, как требует `events.md`.

### 6.2. Интеграционный факт для Telegram

Topic/routing key:
`courier.registration.telegram_notification.created`.

Одна строка outbox и одно AMQP message создаются на каждую пару
`active linked Admin × platform`.

```json
{
  "telegram_id": 123456789,
  "full_name": "Jan Novak",
  "contact_platform": null,
  "contact": null,
  "platform": "foodora"
}
```

| Поле | Тип | Ограничение |
| --- | --- | --- |
| `telegram_id` | integer | `> 0`, помещается в signed 64-bit |
| `full_name` | string | 1–255 |
| `contact_platform` | string/null | максимум 32 |
| `contact` | string/null | максимум 255 |
| `platform` | enum string | `bolt_food`, `foodora`, `wolt` |

Payload намеренно не содержит токен бота, Admin ID, email/phone Courier,
документы или банковские данные. Breaking change контракта требует нового
routing key; молчаливо менять тип или смысл существующих полей нельзя.

### 6.3. AMQP topology и envelope

| Параметр | Значение |
| --- | --- |
| exchange | `domain.events` |
| exchange type | `topic` |
| routing key | `courier.registration.telegram_notification.created` |
| queue | `telegram.notifications` |
| binding | exact routing key |
| durable exchange/queue | `true` |
| delivery mode | persistent |
| content type | `application/json` |
| message ID | UUID строки backend outbox |
| retry delay | 30 000 ms |
| retry entities | `telegram.notifications.retry`, `telegram.notifications.retry.return` |
| DLX / DLQ | `telegram.notifications.dlx` / `telegram.notifications.dlq` |
| bot prefetch | `1` для MVP |

Backend admin manifest объявляет `TopologyDecl` для этой очереди **без**
`ConsumerDecl`. Это необходимо, потому что внутренняя backend queue уже
привязана к `domain.events` по `#`: если целевой Telegram binding отсутствует,
publisher всё равно получит подтверждение от внутренней очереди, а будущий bot
service пропустит событие. Backend worker объявляет topology до запуска outbox
relay, поэтому queue будет существовать даже при выключенном боте.

Bot service при старте пассивно проверяет topology и ждёт её появления; он не
создаёт сущности с отличающимися аргументами. Расхождение durable/DLX/retry
параметров считается ошибкой конфигурации и не скрывается.

Из-за существующего binding `domain.events.subscribers -> #` финальный topic
также попадёт во внутренний backend consumer и будет подтверждён с
`domain_events.no_subscribers`. Это ожидаемый warning текущей архитектуры;
убирать его no-op подписчиком нельзя.

## 7. Изменения backend

### 7.1. `courier_module`

Рабочая сессия:

```bash
codex --cd apps/backend/src/app/modules/courier_module
```

Использовать skills `courier-module` и `background-effect`.

План изменения:

1. Добавить `events.py` с owner-классом `CourierRegistered`, topic
   `courier.registered` и контрактом из раздела 6.1.
2. В `services/couriers.py::_finalize_new_aggregate()` вызвать `emit()` только
   после успешного `INSERT ... RETURNING`; платформы брать из нормализованного
   request в его порядке.
3. Не менять endpoint, S3/staging orchestration и natural-key семантику.
4. Обновить `courier_module/AGENTS.md` и local skill/reference, указав событие
   как часть final transaction.
5. Расширить `tests/test_courier_module.py`.

Обязательные тесты:

- happy path создаёт ровно один `courier.registered` с точным payload;
- event и Courier откатываются вместе при ошибке final transaction;
- запрос с документами по-прежнему атомарно создаёт `file.confirmed` и новый
  Courier event;
- natural-key `200` не добавляет event;
- конкурентные одинаковые POST дают один Courier event;
- последующий `POST /{id}/platform-accounts` не создаёт регистрацию заново;
- manifest и архитектурные тесты остаются зелёными.

Миграция БД не нужна.

### 7.2. `admin` module

Рабочая сессия:

```bash
codex --cd apps/backend/src/app/modules/admin
```

Использовать skills `admin-auth` и `background-effect`; правила
`events.md`, `background-work.md`, `transactions.md`, `layers.md`.

План изменения:

1. Добавить в `admin/events.py`:
   - локальную проекцию чужого `courier.registered`;
   - owner-событие интеграционного контракта
     `courier.registration.telegram_notification.created`.
2. Добавить `admin/subscribers.py` с `@subscribe` handler. Handler только
   передаёт событие и открытую session в admin service.
3. Добавить сервис fan-out, который выбирает
   `Admin.is_active IS TRUE AND Admin.telegram_id IS NOT NULL` и синхронным
   `emit()` создаёт одно событие на каждую пару recipient × platform.
4. Зарегистрировать subscriber и `TopologyDecl` в `admin/module.py`; backend
   consumer для `telegram.notifications` не добавлять.
5. Обновить `admin/AGENTS.md`; auth-модель, PATCH и миграции не менять.
6. Исправить устаревший Telegram-пример в `apps/backend/README.md:280`: сейчас
   он показывает внешний HTTP-вызов внутри subscriber transaction и импорт
   события другого business module, что противоречит актуальным правилам.

Обязательные тесты:

- несколько active linked Admin дают ожидаемый fan-out;
- inactive Admin и Admin с null ID исключены;
- отсутствие получателей — успешный no-op;
- cardinality равна `admins × platforms`;
- nullable contact проходит без преобразования;
- повтор `courier.registered` с тем же AMQP `message_id` не создаёт второй
  fan-out благодаря `processed_messages`;
- падение подписчика откатывает и mark, и все notification outbox rows;
- Telegram ID snapshot в готовом payload не меняется после последующего PATCH;
- manifest содержит subscriber/topology с точными именами.

Миграция БД не нужна.

## 8. Новый сервис `apps/telegram-bot`

### 8.1. Технологическая граница

Сервис — самостоятельный Python 3.12 worker. Для sending-only MVP не нужен
framework входящих Telegram updates: достаточно асинхронного HTTP-клиента к
Bot API и `aio-pika` для RabbitMQ. Рекомендуемый минимальный набор:

- `aio-pika`;
- `httpx` или другой один async HTTP client;
- `pydantic` + `pydantic-settings`;
- `structlog`;
- `pytest`, `pytest-asyncio`, `ruff`, `mypy` в dev/test groups;
- `uv.lock` с зафиксированными версиями.

Не импортировать код из `apps/backend`: queue payload и topology — межсервисный
контракт, а не Python-зависимость.

### 8.2. Предлагаемая структура

```text
apps/telegram-bot/
├── AGENTS.md
├── .agents/skills/telegram-notification/SKILL.md
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── Makefile
├── README.md
├── pyproject.toml
├── uv.lock
├── src/telegram_bot/
│   ├── __init__.py
│   ├── config.py
│   ├── contracts.py
│   ├── logging.py
│   ├── rabbitmq.py
│   ├── rendering.py
│   ├── telegram.py
│   └── worker.py
└── tests/
    ├── test_config.py
    ├── test_contracts.py
    ├── test_rabbitmq.py
    ├── test_rendering.py
    ├── test_telegram.py
    └── test_worker.py
```

`AGENTS.md` фиксирует команды, queue contract, запрет логирования PII/token,
ACK/retry/DLQ matrix и graceful shutdown. Service-specific skill хранит
повторяемый workflow изменения consumer/formatter.

### 8.3. Startup и shutdown

1. Загрузить settings через `pydantic-settings`; token хранить как `SecretStr`.
2. Проверить token вызовом `getMe` **до** начала consume. Ошибка авторизации
   роняет startup, не отправляя накопленные сообщения в DLQ.
3. Открыть robust RabbitMQ connection с понятным connection name.
4. Пассивно дождаться `telegram.notifications` и начать consume с prefetch 1.
5. На SIGTERM прекратить брать новые сообщения, дождаться in-flight не дольше
   configured shutdown timeout, затем закрыть HTTP/Rabbit clients. Не
   подтверждённое сообщение брокер доставит снова.

Worker не слушает HTTP-порт. Как и backend worker, он не получает фиктивный
Docker healthcheck: Docker уже отслеживает завершение процесса.

### 8.4. Рендеринг

Отправлять plain text без `parse_mode`, чтобы пользовательские `full_name` и
`contact` не интерпретировались как Markdown/HTML.

```text
Новая регистрация курьера
Имя: Jan Novak
Контакт: telegram — @jan
Платформа: Wolt
```

Fallback:

```text
Контакт: не указан
```

Display mapping: `bolt_food -> Bolt Food`, `foodora -> Foodora`,
`wolt -> Wolt`. Текст остаётся существенно короче ограничения `sendMessage`
в 4096 символов.

### 8.5. ACK/retry/DLQ matrix

| Ситуация | Действие |
| --- | --- |
| Успешный `sendMessage` | ACK |
| Невалидный JSON/schema/content type/message ID | сразу DLQ, без retry |
| Network timeout/connect error | confirmed publish в retry, затем ACK исходного |
| Telegram 429 | учесть `parameters.retry_after`, затем retry |
| Telegram 5xx | retry |
| Telegram 400/403 для chat ID (не найден, не запускал бота, заблокировал) | сразу DLQ |
| Telegram 401 token error | остановить consumer/process; сообщение оставить unacked |
| Исчерпан `TELEGRAM_MAX_RETRIES` | DLQ |

При перекладывании в retry сохраняются body, routing key, content type,
`message_id`, correlation headers и увеличивается `x-retry-attempt`. Исходное
сообщение ACK'ается только после publisher confirm на retry copy. Для 429
повтор не должен происходить раньше `retry_after`; если fixed retry TTL меньше,
worker ждёт оставшуюся паузу асинхронно, не вызывая Telegram преждевременно.

В MVP сервис не заводит собственную БД: ACK после подтверждённого Telegram
ответа даёт стандартную at-least-once семантику. `message_id` обязателен для
корреляции логов и расследования дублей, но не устраняет неразрешимое окно
между внешним side effect и ACK.

### 8.6. Настройки сервиса

`apps/telegram-bot/.env.example` документирует те же defaults, что и код:

```dotenv
APP_ENV=local
APP_NAME=telegram-bot
LOG_LEVEL=INFO
LOG_FORMAT=console
RABBITMQ_DSN=amqp://guest:guest@localhost:5672/
TELEGRAM_BOT_TOKEN=
TELEGRAM_MAX_RETRIES=5
TELEGRAM_API_TIMEOUT=10
TELEGRAM_SHUTDOWN_TIMEOUT=30
```

Token обязателен для рабочего запуска, не имеет рабочего default, не попадает
в image/build args/логи и задаётся локально в игнорируемом `infra/.env`, а в
production — через secret manager.

### 8.7. Тесты сервиса

- строгая валидация точного payload и enum;
- корректный plain-text formatter и null fallback;
- token не появляется в repr settings и логах;
- startup `getMe` до consume;
- success → один `sendMessage` и ACK;
- network/429/5xx → retry с сохранённым `message_id`;
- permanent 4xx/invalid payload → DLQ;
- retry limit;
- publisher confirm до ACK исходного сообщения;
- SIGTERM прекращает consume и корректно обрабатывает in-flight;
- redelivery после падения до ACK;
- contract/integration тесты используют stub HTTP server, а не настоящий
  Telegram API.

## 9. Изменения `infra/` и контекста Codex

### 9.1. Compose

В `infra/docker-compose.apps.yml` добавить `telegram-bot`:

- `build.context: ../apps/telegram-bot`;
- `restart: unless-stopped`;
- без публичных ports и без healthcheck;
- `stop_grace_period: 40s` при внутреннем timeout 30s;
- внутренний `RABBITMQ_DSN` на `rabbitmq:5672`;
- передавать только нужные env variables, **не** общий `env_file`, чтобы bot не
  получал JWT, PostgreSQL, MinIO и admin bootstrap secrets.

`infra/.env.example` получает документированные
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_MAX_RETRIES`, `TELEGRAM_API_TIMEOUT`,
`TELEGRAM_SHUTDOWN_TIMEOUT`. Локальный `infra/.env` не коммитится.

Отдельные Make targets для жизненного цикла не нужны: существующие `up-apps`,
`reboot-apps`, `down-apps`, `delete-apps` автоматически включат новый service.

### 9.2. Репозиторный контекст

В root-scoped change:

- добавить `apps/telegram-bot/AGENTS.md` до первой service-scoped сессии;
- добавить команду `codex --cd apps/telegram-bot` в root `AGENTS.md` и
  `docs/codex-context.md`;
- проверить `scripts/check-agent-context.sh`: сейчас он автоматически обходит
  все каталоги `apps/*`, поэтому отдельная строка, вероятно, не нужна;
- обновить карту сервисов/README, если она появится в ходе реализации.

## 10. Наблюдаемость, безопасность и privacy

- Структурные логи содержат `message_id`, topic, attempt, Telegram status/error
  class и длительность, но не token, `full_name`, `contact` или весь payload.
- Минимальные события: `telegram.consumer_started`,
  `telegram.notification_sent`, `telegram.notification_retrying`,
  `telegram.notification_dead_lettered`, `telegram.shutdown_timed_out`.
- Алертовать на рост `telegram.notifications.dlq`, повторяющиеся 401 и
  отсутствие consumer у основной queue.
- RabbitMQ management содержит payload/DLQ с PII. В production нужны отдельный
  RabbitMQ user/vhost с минимальными permissions, ограниченный доступ к UI и
  операционная процедура разбора/удаления DLQ.
- Plain text предотвращает markup injection; URL preview лучше отключить.
- Token меняется через secret store и никогда не хранится в Git.
- Admin обязан заранее открыть бота и нажать `/start`; одного корректного ID
  недостаточно, чтобы бот мог начать личный диалог. Это должно быть написано в
  README/операционной инструкции.

## 11. Разработка

Перед началом: рабочее дерево сейчас содержит незавершённые пользовательские
изменения, включая рефакторинг `courier_module/services.py -> services/` и
frontend-файлы. Их нельзя reset/stash/перезаписывать без владельца. Сначала
довести их до отдельного коммита либо явно отделить от этой задачи.

Команды ниже запускаются из корня репозитория. После запуска команды текст из
соответствующего блока `Промпт` нужно отправить в открывшуюся сессию Codex.
Backend разбит на две module-scoped сессии: одна меняет владельца Courier, вторая
— владельца Admin. Объединять их в одну длинную root-сессию не нужно.

### 11.1. Подготовка контекста нового сервиса

Запуск:

```bash
codex --cd .
```

Промпт:

```text
Подготовь контекст для нового отдельного сервиса apps/telegram-bot согласно
notification_spec.md, но пока не реализуй consumer и не меняй backend или infra.

Сделай только root bootstrap из разделов 9.2 и 11.1 спецификации:
- создай минимальный apps/telegram-bot/AGENTS.md;
- создай service-specific skill telegram-notification с инвариантами точного
  queue contract, ACK/retry/DLQ и запретом логирования token/PII; для создания
  skill используй system skill skill-creator;
- обнови root AGENTS.md и docs/codex-context.md командой запуска нового сервиса;
- проверь scripts/check-agent-context.sh и поправь его только если новый service
  не покрывается текущим автоматическим обходом apps/*.

Сначала проверь git status и сохрани все существующие пользовательские изменения.
Не делай reset, stash или переписывание несвязанных файлов. Выполни проверки
контекста, затем создай отдельный conventional commit через skill git-commit:
chore(telegram-bot): scaffold service context
```

Результат этой сессии — только корректная цепочка инструкций, позволяющая
следующую сессию запустить непосредственно из `apps/telegram-bot`.

### 11.2. Backend: событие владельца Courier

Запуск:

```bash
codex --cd apps/backend/src/app/modules/courier_module
```

Промпт:

```text
Реализуй первый backend-этап Telegram-уведомлений по notification_spec.md:
разделы 3, 5, 6.1, 7.1, 10 и acceptance criteria раздела 12.

Работай только в области courier_module и относящихся к ней backend-тестах.
Обязательно используй локальные skills courier-module и background-effect,
прочитай ближайшие AGENTS.md и релевантные backend rules по events,
transactions, background-work и layers.

Требуемый результат:
- добавить owner-event CourierRegistered с topic courier.registered;
- payload: courier_id, full_name, nullable contact_platform/contact и все
  platform accounts;
- emit выполнить ровно один раз внутри winner-ветки финальной transaction
  _finalize_new_aggregate, атомарно с фактическим INSERT Courier;
- natural-key повтор, concurrent loser и добавление platform account к уже
  существующему Courier не должны создавать событие;
- не менять HTTP-контракт, staging/S3 orchestration, admin module, Telegram
  service или infra;
- обновить courier_module AGENTS/local reference и добавить тесты из раздела 7.1.

Сначала проверь git status: в этой области может находиться пользовательский
рефакторинг services.py -> services/. Не откатывай и не перезаписывай его;
интегрируй изменение в актуальную структуру. Выполни из apps/backend make check,
make test и uv run alembic check. Затем используй backend pre-commit и skill
git-commit, создав отдельный commit:
feat(courier): publish registration event
```

### 11.3. Backend: Admin fan-out и Telegram topology

Запускать после фиксации контракта `courier.registered` из предыдущей сессии.

```bash
codex --cd apps/backend/src/app/modules/admin
```

Промпт:

```text
Реализуй второй backend-этап Telegram-уведомлений по notification_spec.md:
разделы 3, 5, 6.1-6.3, 7.2, 10 и acceptance criteria раздела 12.

Работай в области admin module и относящихся к ней backend integration tests.
Используй skills admin-auth и background-effect, ближайшие AGENTS.md и правила
events, background-work, transactions и layers. Не импортируй event class или
модели courier_module: межмодульный контракт — topic и локальная Pydantic-схема.

Требуемый результат:
- добавить локальную проекцию courier.registered;
- добавить @subscribe handler, зарегистрированный в admin_module;
- сервис выбирает только Admin.is_active IS TRUE и telegram_id IS NOT NULL;
- в той же transaction с processed_messages создать через emit один точный
  пяти-полевой notification event на каждую пару Admin x platform;
- topic: courier.registration.telegram_notification.created;
- объявить в admin manifest durable TopologyDecl для domain.events ->
  telegram.notifications с exact binding, retry 30000 ms и DLQ, но не добавлять
  backend ConsumerDecl для этой очереди;
- не менять Admin.telegram_id schema/API и не создавать миграцию;
- исправить устаревший Telegram/outbox пример в apps/backend/README.md;
- реализовать все тесты fan-out, rollback, replay и topology из раздела 7.2.

Не меняй courier_module, Telegram service или infra. Сохрани несвязанные
пользовательские изменения. Выполни из apps/backend make check, make test и
uv run alembic check. Затем используй backend pre-commit и skill git-commit,
создав отдельный commit:
feat(admin): prepare courier telegram notifications
```

После двух backend-сессий при необходимости можно открыть короткую
интеграционную backend-сессию из `apps/backend`, но только для исправления
общесервисных тестов/контрактов, которые нельзя отнести к одному модулю. Новую
функциональность в ней добавлять не нужно.

### 11.4. Telegram bot service

Запускать после сессии 11.1; контракт раздела 6 должен оставаться неизменным.

```bash
codex --cd apps/telegram-bot
```

Промпт:

```text
Реализуй отдельный sending-only Telegram notification service строго по
notification_spec.md: разделы 3, 4, 6.2-6.3, 8, 10 и acceptance criteria
раздела 12. Сначала полностью прочитай apps/telegram-bot/AGENTS.md и локальный
skill telegram-notification.

Требуемый результат:
- самостоятельный Python 3.12 + uv service без импортов из apps/backend;
- exact payload: telegram_id, full_name, nullable contact_platform/contact,
  platform; queue telegram.notifications; routing key
  courier.registration.telegram_notification.created;
- aio-pika consumer с robust connection, passive topology check, prefetch=1,
  обязательным AMQP message_id и graceful SIGTERM shutdown;
- async Telegram Bot API client: getMe до consume и plain-text sendMessage без
  parse_mode, безопасный formatter и display mapping платформ;
- ACK только после успешной отправки;
- invalid payload/permanent 4xx -> DLQ, network/429/5xx -> confirmed retry с
  сохранением message_id/headers, 401 token error останавливает consumer;
- учесть Telegram retry_after и лимит TELEGRAM_MAX_RETRIES;
- pydantic-settings, SecretStr token, структурные no-PII/no-token logs;
- pyproject.toml, uv.lock, Dockerfile builder/runtime с non-root user, Makefile,
  .env.example, README и полный набор тестов из раздела 8.7;
- тесты используют stub Telegram API, а не реальный token или сеть.

Не реализуй polling/webhook или /start linking, не добавляй БД и не меняй
backend/infra. Проверь существующие изменения перед работой и сохрани всё
несвязанное. Выполни make check и make test; container image будет проверен
позже только через infra. Затем используй skill git-commit, создав commit:
feat(telegram-bot): deliver courier notifications
```

Эта сессия может идти параллельно с backend-сессиями после завершения root
bootstrap и фиксации контрактов раздела 6.

### 11.5. Infra wiring

Запуск:

```bash
codex --cd infra
```

Промпт:

```text
Подключи готовый apps/telegram-bot к стеку строго по разделам 9.1, 10, 11.5 и
12 notification_spec.md. Прочитай infra/AGENTS.md, сначала выполни make help и
используй skill infra-check.

Добавь telegram-bot в docker-compose.apps.yml без ports и фиктивного
healthcheck, с restart unless-stopped и stop_grace_period 40s. Не передавай
общий env_file: явно передай только RabbitMQ, logging и TELEGRAM_* settings.
Добавь документированные переменные в infra/.env.example; не читай и не
коммить локальный infra/.env. Backend, bot code и инфраструктурные сервисы не
меняй. Выполни make check и сборку/перезапуск только через make -C infra.
Затем используй skill git-commit и создай commit:
feat(infra): run telegram notification service
```

### 11.6. Интеграционная проверка

Запуск: `codex --cd .` или `codex --cd infra`.

- прогнать проверки обоих сервисов и `make -C infra check`;
- поднять стек через `make -C infra up`;
- E2E со stub Telegram API: создать linked active Admin, сделать фактический
  `POST /courier`, дождаться relay/fan-out и проверить один `sendMessage` на
  каждую пару Admin × platform;
- повторить тот же natural-key POST и доказать отсутствие новых отправок;
- остановить bot, создать Courier, убедиться, что queue накапливает сообщение,
  затем поднять bot и получить доставку;
- проверить transient retry и permanent DLQ;
- выполнить ручной smoke с тестовым BotFather token и Admin, нажавшим `/start`;
- исправления коммитить в области сервиса-владельца, не смешивая сервисы без
  общей причины.

## 12. Acceptance criteria / Definition of Done

- [ ] Фактически новый Courier создаёт один `courier.registered`; repeat/loser —
  ни одного.
- [ ] Courier commit и внутренний outbox event атомарны.
- [ ] Только active Admin с non-null Telegram ID становятся получателями.
- [ ] В `telegram.notifications` появляется ровно `admins × platforms`
  persistent messages с точным пяти-полевым JSON.
- [ ] Queue, retry и DLQ существуют до первой публикации.
- [ ] Backend не вызывает RabbitMQ/Telegram из HTTP или открытой business
  transaction.
- [ ] Bot успешно отправляет plain-text `sendMessage` и ACK'ает только после
  успеха.
- [ ] Transient ошибки повторяются, permanent ошибки и исчерпанный retry уходят
  в DLQ.
- [ ] Bot корректно переживает RabbitMQ/Telegram outage и graceful shutdown.
- [ ] Token и Courier PII не появляются в логах; token не попадает в Git/image.
- [ ] Admin, не выполнивший `/start`, даёт диагностируемый permanent failure,
  а не бесконечный retry.
- [ ] Backend, bot, infra и root context checks проходят.
- [ ] Каждая область завершена conventional commit через `git-commit`.

## 13. Риски и осознанные ограничения

| Риск | Решение MVP |
| --- | --- |
| Несколько платформ у Courier | отдельное уведомление на каждую platform по точному контракту пользователя |
| Queue ещё не создана | backend заранее объявляет topology до outbox relay |
| Бот выключен | durable queue хранит backlog |
| Telegram rate limit | prefetch 1, 429 + `retry_after`, retry queue |
| Неверный/заблокированный chat | permanent DLQ и операционная диагностика |
| Дубль после успешного send до ACK | принят как at-least-once ограничение MVP |
| PII в Telegram и DLQ | минимальный payload, no-PII logs, ограниченный RabbitMQ access, compliance gate |
| Невозможно выбрать «создавшего Admin» | POST Courier публичный; уведомляются все active linked Admin |
| Шум `no_subscribers` в backend | известное следствие catch-all queue; не маскировать no-op subscriber |

## 14. Внешняя предпосылка Telegram

По официальному Bot API `sendMessage` принимает `chat_id` и текст, успешный
вызов возвращает Message; flood-control error может вернуть
`parameters.retry_after`. Администратор личного чата должен сначала начать
диалог с ботом. Реализация и runbook должны опираться на актуальные официальные
страницы:

- <https://core.telegram.org/bots/api#sendmessage>
- <https://core.telegram.org/bots/api#responseparameters>
- <https://core.telegram.org/bots#how-do-bots-work>
- <https://core.telegram.org/bots/faq>
