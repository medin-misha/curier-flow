# backend-template

Шаблон backend-сервиса: **FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL**.

Инфраструктура уже написана — транзакции, доменные события, идемпотентность,
фоновый процесс, миграции, тесты на настоящих контейнерах. Вы пишете только
бизнес-модули: `git clone` → заполнить `.env` → создать модуль → запустить.

- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Что уже готово из коробки](#что-уже-готово-из-коробки)
- [Архитектура](#архитектура)
- [Как добавить модуль](#как-добавить-модуль)
- [Outbox на примере: Courier → уведомление в Telegram](#outbox-на-примере-courier--уведомление-в-telegram)
- [Воркер: что в нём живёт и почему не в uvicorn](#воркер-что-в-нём-живёт-и-почему-не-в-uvicorn)
- [Команды](#команды)
- [Документация](#документация)

## Требования

| Что | Зачем |
| --- | --- |
| **Docker** с Compose plugin | PostgreSQL, RabbitMQ, Redis, MinIO; тесты поднимают свои контейнеры через testcontainers |
| **[uv](https://docs.astral.sh/uv/)** | зависимости и запуск: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **make** | команды разработки backend и управление стеком через `infra/` |

Python ставить отдельно не нужно: версию из `.python-version` (3.12) uv скачает
сам.

## Быстрый старт

Все команды выполняются из корня репозитория. Единственная точка запуска и
управления контейнерами — `infra/`:

```bash
cp infra/.env.example infra/.env
make -C apps/backend install
make -C infra up
make -C infra caddy-ca
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain infra/secrets/caddy-root.crt
curl -s https://backend.localhost/health/ready
```

Перед первым `make -C infra up` замените пример
`ADMIN_BOOTSTRAP_PASSWORD=change-me-before-first-start` в `infra/.env` на свой
секрет длиной 12–128 символов. `ADMIN_BOOTSTRAP_USERNAME` задаёт логин первого
администратора, а необязательный положительный `ADMIN_BOOTSTRAP_TELEGRAM_ID` —
его Telegram user ID. Bootstrap выполняется только при пустой таблице `admins`;
после создания администратора bootstrap credentials можно удалить из
`infra/.env`.

Caddy выпускает сертификаты через локальный CA, сохранённый в Docker volume.
Команда `caddy-ca` экспортирует его в игнорируемый Git файл, а `security`
добавляет root в системное хранилище доверия macOS. После `delete-logging`
создаётся новый CA, поэтому старый сертификат нужно удалить из Keychain и
установить новый. Без изменения системного trust store запросы можно проверять
с `curl --cacert infra/secrets/caddy-root.crt ...`.

Telegram worker для запуска остального стека необязателен. Если
`TELEGRAM_BOT_TOKEN` пуст, `make -C infra up` выводит предупреждение, не создаёт
его контейнер и продолжает запуск. Чтобы включить worker, задайте token в
игнорируемом `infra/.env` или в shell-окружении; значение из shell имеет
стандартный приоритет Compose над файлом.

В ответ приходит

```json
{"status":"ready","dependencies":[
  {"name":"database","status":"up","duration_ms":9.1,"error":null},
  {"name":"broker","status":"up","duration_ms":10.2,"error":null},
  {"name":"storage","status":"up","duration_ms":28.0,"error":null}]}
```

— база, брокер и объектное хранилище отвечают, сервис готов принимать запросы.

Что произошло:

1. `infra/.env` — единое окружение всего docker-стека;
2. `make -C apps/backend install` — зависимости всех групп и git-хуки;
3. `make -C infra up` последовательно поднимает PostgreSQL, RabbitMQ, Redis и
   MinIO до healthy, собирает образ API и запускает одноразовый контейнер с
   `alembic upgrade head`, а затем собирает и поднимает приложения. Команда
   Alembic переопределяет command сервиса `api`, поэтому uvicorn и lifespan на
   этапе миграции не стартуют. Когда API запускается, таблица `admins` уже
   существует и lifespan может создать первого администратора. Telegram worker
   запускается только при непустом `TELEGRAM_BOT_TOKEN`;
4. проверка готовности.

Дальше можно потрогать шаблон руками:

```bash
curl -s https://backend.localhost/health/info # {"name":...,"version":...,"revision":"8f4f401e3143"}
curl -s https://backend.localhost/files       # {"items":[],"next_cursor":null} — пустая keyset-страница
open https://backend.localhost/docs           # Swagger (DEBUG=true)
open https://localhost                        # публичный сайт
open https://admin.localhost                  # Admin
open https://grafana.localhost                # Grafana
open http://localhost:15672                   # RabbitMQ, guest/guest
```

### Применить изменения backend

Процессы backend не запускаются отдельно с хоста. После изменения кода
пересоберите и пересоздайте контейнеры приложений через `infra/`:

```bash
make -C infra reboot-apps
```

Инфраструктура и её данные при этом сохраняются.

### Остановить

```bash
make -C infra down         # остановить, данные в volume'ах остаются
make -C infra delete       # остановить и удалить данные с подтверждением
```

## Что уже готово из коробки

**Ядро запроса**

- одна транзакция на запрос, коммит делает зависимость, и он гарантированно
  происходит **до отправки ответа**: клиент не может получить 2xx на
  несохранённые данные;
- keyset-пагинация с непрозрачным курсором — без `OFFSET`, без пропусков и
  дублей на подвижных данных;
- все ошибки в формате RFC 9457 `application/problem+json` — доменные, ошибки
  валидации, 404 маршрутизатора и необработанные исключения;
- `Idempotency-Key` для записывающих ручек: одна метка `@idempotent`, повтор
  возвращает сохранённый ответ, а не создаёт вторую сущность;
- структурные логи (structlog) со сквозным `request_id`, JSON в проде и
  читаемый вывод локально.

**Доменные события**

- transactional outbox: событие пишется той же транзакцией, что и данные;
- релей публикует накопленное в RabbitMQ с экспоненциальной отсрочкой и DLQ;
- подписчики модулей получают событие вместе с отметкой `processed_messages` —
  повторная доставка безвредна;
- модули общаются **только** событиями и не импортируют друг друга.

**Фон**

- один процесс `worker.py`: TaskIQ, его шедулер, консьюмеры RabbitMQ и релей;
- периодические задачи объявляются меткой `@schedule(cron=...)`;
- уборка служебных таблиц (outbox, ключи идемпотентности, отметки сообщений)
  уже настроена;
- корректная остановка по SIGTERM: начатая работа доделывается.

**Хранилище файлов**

- модуль `storage`: двухфазная загрузка через presigned URL. Файлы **не
  проходят через backend** — ни на загрузке, ни на скачивании;
- сборка брошенных загрузок и отложенное удаление объектов.

**Эксплуатация**

- модуль `health`: `/health/live`, `/health/ready`, `/health/info` —
  с правильным разделением liveness и readiness;
- `Dockerfile` с отдельными целями `api` и `worker`, compose-файлы в `infra/`
  со всем стеком, healthcheck'и настроены;
- JWT (access/refresh) и argon2 для паролей в `kernel/security`.

**Контроль качества**

- `ruff` (формат + ~25 групп правил, включая запрет `HTTPException`, наивного
  UTC и `os.environ`), `mypy` (строгий, особенно строгий к ядру),
  `import-linter` (правила слоёв), `pre-commit`, локальные `make check` и
  `make test`;
- 400+ тестов на настоящих Postgres, RabbitMQ, Redis и MinIO через
  testcontainers, включая архитектурные проверки: «хендлер не ходит в базу»,
  «сервис не знает про HTTP», «модуль не коммитит», «каждый модуль в реестре».

**AI-native**

- выбирайте минимальный рабочий каталог OpenCode: `apps/backend/` для общей
  задачи, `apps/backend/src/app/modules/<name>/` для существующего модуля;
- `AGENTS.md` содержит только обязательные инварианты и маршрутизацию;
- `.agents/rules/` хранит подробные backend-правила по типам изменений;
- `.agents/skills/` хранит backend-процессы: `new-module`,
  `background-effect`, `db-migration`, `pre-commit`;
- у сложного модуля есть короткий `AGENTS.md` и локальный skill с
  тематическими `references/`.

Схема рабочих областей и контекстные бюджеты описаны в
[корневом `AGENTS.md`](../../AGENTS.md).

## Архитектура

```
                        ┌───────────────────────────────┐
   HTTP-клиент ────────▶│  процесс api  (uvicorn)       │
                        │  main.py → create_app         │
                        │  ┌─────────────────────────┐  │
                        │  │ api/  router, errors,   │  │
                        │  │       middleware, deps  │  │
                        │  └───────────┬─────────────┘  │
                        │  ┌───────────▼─────────────┐  │
                        │  │ modules/ handlers →     │  │
                        │  │          services       │  │
                        │  └───────────┬─────────────┘  │
                        └──────────────┼────────────────┘
                                       │ одна транзакция:
                                       │ данные + строка outbox
                                       ▼
                        ┌───────────────────────────────┐
                        │        PostgreSQL             │
                        │  бизнес-таблицы               │
                        │  outbox                       │
                        │  idempotency_keys             │
                        │  processed_messages           │
                        └──────┬────────────────▲───────┘
                               │ релей забирает │ подписчик пишет
                               │ неопубликованное      в той же
                               ▼                │ транзакции, что и отметка
                        ┌───────────────────────┴───────┐
                        │  процесс worker               │
                        │  worker.py                    │
                        │  ├─ релей outbox (TaskIQ)     │
                        │  ├─ шедулер: задачи модулей   │
                        │  ├─ консьюмер доменных событий│
                        │  └─ консьюмеры внешних очередей│
                        └──────┬─────────────────▲──────┘
                               │ publish         │ consume
                               ▼                 │
                        ┌──────────────────────────────┐
                        │  RabbitMQ                    │
                        │  domain.events (topic)       │
                        │  domain.events.subscribers   │
                        │  + retry / DLQ               │
                        └──────────────────────────────┘

              Redis — результаты задач TaskIQ
              MinIO/S3 — объекты; клиент ходит туда напрямую по presigned URL
```

### Правила зависимостей

```
app.api  ──▶  app.modules  ──▶  app.platform  ──▶  app.kernel
```

Стрелка означает «вправе импортировать». Обратных стрелок нет:

- `kernel` не знает ни про `fastapi`, ни про брокер, ни про модули — поэтому
  им пользуются и воркер, и миграции;
- `platform` — адаптеры к внешнему миру (RabbitMQ, TaskIQ, S3), про бизнес не
  знает;
- **модули не импортируют друг друга** — только доменные события;
- модуль не импортирует `app.api`: нужные псевдонимы зависимостей он объявляет
  у себя из тех же функций ядра.

Правило проверяет `uv run lint-imports`, а не ревьюер.

### Раскладка модуля

```
src/app/modules/orders/
  handlers.py            только HTTP: разобрал запрос, позвал сервис, собрал ответ
  services.py            бизнес-логика; единственное место CRUD и emit()
  models/                ORM-модели (пакет: его импортирует alembic)
  schemas/requests.py    что клиент вправе прислать
  schemas/responses.py   что отдаём наружу
  events.py              доменные события модуля
  subscribers.py         обработчики чужих событий
  tasks.py               периодические задачи
  module.py              манифест Module — всё, что модуль отдаёт приложению
  AGENTS.md              правила модуля
```

Файла, которому нечего содержать, нет: модуль `health` обходится без `models/`
и `subscribers.py`, и в его `AGENTS.md` объяснено почему.

Состав сервиса объявлен в одном месте — `src/app/modules/__init__.py`:

```python
MODULES: Final[tuple[Module, ...]] = (health_module, storage_module, orders_module)
```

Из этого списка собираются роутер, lifespan, метаданные Alembic, задачи,
подписчики и топология брокера. Модуля нет в списке — значит, его нет в
приложении.

## Как добавить модуль

Не пишите каркас руками — начните OpenCode-сессию с рабочим каталогом
`apps/backend/` и используйте skill **`.agents/skills/new-module/SKILL.md`**.
Скажите агенту «создай модуль orders с ресурсом заказов и событием о создании»,
и он пройдёт весь путь: файлы, манифест, строка в `MODULES`, миграция,
`AGENTS.md` модуля, тесты.

Скилл знает то, что легко забыть:

- какие файлы **не** создаются, если содержания нет;
- что попадает в схему запроса, а что передаётся через `**overrides`
  (владелец, статус, ключ — их клиент задавать не должен);
- обязательный составной индекс `(created_at DESC, id DESC)` для таблиц,
  которые листают;
- `__patchable__` — белый список полей для PATCH;
- `scope="function"` у зависимости пишущей транзакции;
- чем `emit()` отличается от `after_commit`.

Проверка простая: модуль, созданный по скиллу, проходит `make check` и
`make test` без правок, а `git status` показывает изменения **только** внутри
каталога модуля плюс одну строку в `MODULES` (плюс миграция и тесты).

## Outbox на примере: Courier → уведомление в Telegram

Задача: после фактического создания Courier отправить каждому активному Admin
с заданным `telegram_id` по одному сообщению на каждую платформу Courier.
`courier_module` ничего не знает про Admin и Telegram; Admin строит локальную
проекцию события и fan-out, а Telegram отправляет отдельный внешний worker.

### 1. Courier сообщает о факте

Владелец события объявляет полный межмодульный факт:

```python
# src/app/modules/courier_module/events.py
class CourierRegistered(DomainEvent):
    topic: ClassVar[str] = "courier.registered"

    courier_id: UUID
    full_name: str = Field(min_length=1, max_length=255)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    platforms: list[DeliveryPlatform] = Field(min_length=1, max_length=3)
```

Только winner-ветка `_finalize_new_aggregate()` после успешного `INSERT Courier`
создаёт событие:

```python
# src/app/modules/courier_module/services/couriers.py
emit(
    session,
    CourierRegistered(
        courier_id=inserted_id,
        full_name=request.full_name,
        contact_platform=request.contact_platform,
        contact=request.contact,
        platforms=[account.platform for account in request.platform_accounts],
    ),
)
```

`emit()` ничего не отправляет в сеть. Он делает `session.add()` строки `outbox`
в той же финальной транзакции, что создаёт Courier aggregate. Natural-key
repeat и проигравшая конкурентная вставка не создают `CourierRegistered`.

### 2. Admin строит локальную проекцию и второй outbox-факт

Admin не импортирует класс из `courier_module`: тот же topic описан локальной
Pydantic-схемой. Здесь же объявлен точный пяти-полевый контракт внешнего
Telegram worker:

```python
# src/app/modules/admin/events.py
class DeliveryPlatform(StrEnum):
    BOLT_FOOD = "bolt_food"
    FOODORA = "foodora"
    WOLT = "wolt"


class CourierRegistered(DomainEvent):
    topic: ClassVar[str] = "courier.registered"

    courier_id: UUID
    full_name: str = Field(min_length=1, max_length=255)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    platforms: list[DeliveryPlatform] = Field(min_length=1, max_length=3)


class CourierRegistrationTelegramNotificationCreated(DomainEvent):
    topic: ClassVar[str] = "courier.registration.telegram_notification.created"

    telegram_id: int = Field(gt=0, le=2**63 - 1)
    full_name: str = Field(min_length=1, max_length=255)
    contact_platform: str | None = Field(default=None, max_length=32)
    contact: str | None = Field(default=None, max_length=255)
    platform: DeliveryPlatform
```

Зарегистрированный subscriber передаёт факт транзакционному fan-out сервису:

```python
# src/app/modules/admin/subscribers.py
@subscribe(CourierRegistered)
async def handle_courier_registered(
    event: CourierRegistered,
    session: AsyncSession,
) -> None:
    await fan_out_courier_registration_notifications(event, session=session)
```

Сервис снимает snapshot только активных Admin с non-null `telegram_id` и
создаёт отдельное событие для каждой пары Admin/platform:

```python
# src/app/modules/admin/services/notifications.py
telegram_ids = (
    await session.scalars(
        select(Admin.telegram_id).where(
            Admin.is_active.is_(True),
            Admin.telegram_id.is_not(None),
        )
    )
).all()

for telegram_id in telegram_ids:
    if telegram_id is None:
        continue
    for platform in event.platforms:
        emit(
            session,
            CourierRegistrationTelegramNotificationCreated(
                telegram_id=telegram_id,
                full_name=event.full_name,
                contact_platform=event.contact_platform,
                contact=event.contact,
                platform=platform,
            ),
        )
```

Эти события попадают во второй набор строк `outbox` атомарно с отметкой
`processed_messages` входного `courier.registered`.

### 3. Backend объявляет topology, внешний worker потребляет очередь

Admin-манифест привязывает точный routing key к durable очереди с retry/DLQ:

```python
# src/app/modules/admin/module.py
TELEGRAM_NOTIFICATIONS_TOPOLOGY: Final = TopologyDecl(
    exchange=DOMAIN_EVENTS_EXCHANGE,
    queue="telegram.notifications",
    routing_key=CourierRegistrationTelegramNotificationCreated.topic,
    exchange_type="topic",
    durable=True,
    dead_letter=True,
    retry_ttl_ms=30_000,
)

admin_module: Final = Module(
    name="admin",
    router=router,
    settings=AdminSettings,
    models="app.modules.admin.models",
    subscribers=(handle_courier_registered,),
    tasks=(purge_expired_refresh_tokens,),
    topology=(TELEGRAM_NOTIFICATIONS_TOPOLOGY,),
    lifespan=admin_lifespan(settings=admin_settings),
)
```

`DOMAIN_EVENTS_EXCHANGE` — это `domain.events`. В Admin нет `ConsumerDecl` и у
`admin_module` нет `consumers=`: для этой очереди backend worker только создаёт
topology до запуска релея. Самостоятельный `apps/telegram-bot` пассивно
проверяет очередь `telegram.notifications` и принимает только routing key
`courier.registration.telegram_notification.created`. Его независимая строгая
модель содержит те же пять полей:

```python
# ../telegram-bot/src/telegram_bot/contracts.py
class CourierRegistrationNotification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    telegram_id: StrictInt = Field(gt=0, le=SIGNED_INT64_MAX)
    full_name: FullName
    contact_platform: ContactPlatform | None
    contact: Contact | None
    platform: Platform
```

`Platform` допускает только `bolt_food`, `foodora` и `wolt`; оба nullable-поля
обязаны присутствовать в payload со значением строки или `null`.

Для личной доставки Admin должен заранее открыть бота и нажать `/start`:
одного корректного `telegram_id` недостаточно, чтобы бот начал диалог.
Пяти-полевый payload и DLQ содержат PII, поэтому production-доступ к RabbitMQ
management и права bot-пользователя должны быть минимальными.

### 4. Что происходит между ними

```
POST /courier
   │
   ├─ финальная транзакция:  INSERT Courier aggregate …
   │                         INSERT outbox (
   │                           topic='courier.registered',
   │                           payload={courier_id, full_name,
   │                                    contact_platform, contact, platforms})
   ├─ COMMIT ──────────────── либо есть и aggregate, и событие, либо нет обоих
   └─ 201 Created клиенту; natural-key repeat возвращает 200 без события

   … в это время в процессе backend worker …

   релей: SELECT … WHERE published_at IS NULL FOR UPDATE SKIP LOCKED
          publish → RabbitMQ (
            exchange='domain.events', routing_key='courier.registered')
          UPDATE outbox SET published_at = now()

   backend domain-event consumer:
          INSERT processed_messages (message_id)
          INSERT outbox × (active Admin с telegram_id × platform) (
            topic='courier.registration.telegram_notification.created',
            payload={telegram_id, full_name, contact_platform, contact, platform})
          COMMIT → ACK

   релей: publish courier.registration.telegram_notification.created
          → domain.events → telegram.notifications
   внешний apps/telegram-bot: validate → sendMessage → ACK / retry / DLQ
```

### Почему HTTP-статус в этой цепочке не участвует

Для нового Courier handler возвращает `201`, для natural-key repeat — `200`.
Это описание результата для HTTP-клиента, а не триггер публикации:

- `_finalize_new_aggregate()` вызывает `emit()` только после успешной вставки
  нового Courier; финальный `session.begin()` коммитит aggregate и outbox
  вместе;
- при откате исчезают и бизнес-данные, и строка outbox, поэтому уведомлять не о
  чем;
- при недоступном RabbitMQ Courier уже может быть сохранён, но релей повторит
  публикацию оставшейся строки outbox после восстановления брокера;
- natural-key repeat возвращает `200` без события потому, что нового факта и
  вызова `emit()` не было, а не из-за проверки HTTP-статуса.

Триггер доставки — **успешный коммит**, а не ответ. Событие и данные становятся
видимыми одним `COMMIT`, а релей переживает падение брокера и перезапуск
процесса.

Цена: доставка **at-least-once**. Релей может опубликовать сообщение и упасть
до отметки строки; брокер может доставить его дважды. Поэтому backend subscriber
защищён `processed_messages`, записанным в той же транзакции, что и второй
outbox-факт.

Внешний HTTP-вызов из subscriber transaction запрещён: его нельзя атомарно
связать с `processed_messages`, а блокировка базы будет ждать чужую сеть.
Внешний Telegram worker подтверждает AMQP-сообщение только после успешного
`sendMessage` либо подтверждённой retry copy. Окно «Telegram принял запрос,
worker завершился до ACK» всё равно оставляет допустимый дубль.

### Если потерять не жалко

Для эффектов, потеря которых бизнесу безразлична — прогрев кеша, метрика,
необязательный пинг, — есть `after_commit`. Хук выполняется после успешного
коммита и **никаких гарантий не даёт**: процесс, упавший между коммитом и хуком,
потеряет его молча. Правило выбора одно: если на вопрос «а если этот эффект не
случится?» ответ длиннее одного слова — нужен `emit()`.

## Воркер: что в нём живёт и почему не в uvicorn

Контейнер `worker` из `infra/docker-compose.apps.yml` запускает один процесс
`app.worker`, в котором крутится вся фоновая работа:

| Что | Зачем |
| --- | --- |
| **релей outbox** | забирает неопубликованные строки и отправляет их в RabbitMQ |
| **шедулер TaskIQ** | запускает периодические задачи модулей по их меткам `@schedule` |
| **воркер TaskIQ** | выполняет задачи — и периодические, и поставленные через `kiq()` |
| **консьюмер доменных событий** | доставляет события подписчикам модулей |
| **консьюмеры внешних очередей** | обрабатывают сообщения чужих сервисов |
| **уборка служебных таблиц** | outbox, `idempotency_keys`, `processed_messages` |

Почему всё это не в процессе uvicorn:

- **Перекатка.** Фоновая работа, привязанная к веб-процессу, умирает вместе с
  ним. Пересборка образа посреди обработки сообщения — потерянная работа.
- **Масштабирование.** Веб-процессов обычно несколько. Периодическая задача,
  живущая в них, начинает выполняться N раз одновременно — по разу на воркер
  uvicorn.
- **Профиль нагрузки разный.** HTTP-воркер должен отвечать за миллисекунды;
  задача уборки вправе работать минуту. В одном процессе они мешают друг другу.
- **Ресурсы.** Консьюмер с `prefetch=16` и пул соединений к базе на каждый
  веб-процесс — это умножение и того, и другого на число реплик.

Почему при этом воркер **один**, а не четыре отдельных контейнера: пока у
релея, задач и консьюмеров одинаковый профиль нагрузки, четыре процесса
означали бы четыре пула соединений к базе и четыре места, где можно забыть
выкатить новую версию. Разносить их стоит тогда, когда профиль разойдётся.

Что важно знать при работе с воркером:

- `lifespan` модуля **воркер не исполняет** — он поднимает только приложение
  FastAPI. Клиентов внешних сервисов задача создаёт себе сама;
- задачи обязаны переживать параллельный запуск в нескольких воркерах:
  выборка через `FOR UPDATE SKIP LOCKED`;
- остановка по SIGTERM: сначала перестаём забирать новые сообщения, потом
  ждём начатые (`WORKER_SHUTDOWN_TIMEOUT`), и только затем закрываем
  соединения.

## Команды

| Команда | Что делает |
| --- | --- |
| `make install` | зависимости всех групп и git-хуки |
| `make check` | `ruff format --check`, `ruff check`, `mypy`, `lint-imports` |
| `make test` | pytest с покрытием; отдельный порог 85% на `app.kernel` |
| `make revision m="add orders"` | сгенерировать миграцию по моделям |

Команды выше выполняются из `apps/backend/` и не запускают процессы backend.
Контейнеры и применение миграций управляются только из корня репозитория через
`infra/`:

| Команда | Что делает |
| --- | --- |
| `make -C infra help` | показать команды управления стеком |
| `make -C infra up` | последовательно поднять инфраструктуру, применить миграции и запустить приложения; Telegram worker — только с token |
| `make -C infra up-infra` | поднять только инфраструктуру |
| `make -C infra migrate` | собрать образ API и выполнить `alembic upgrade head` без uvicorn/lifespan |
| `make -C infra reboot-apps` | пересобрать и пересоздать приложения; Telegram worker — только с token |
| `make -C infra down` | остановить весь стек с сохранением данных |

`make check` и `make test` обязаны быть зелёными перед каждым коммитом. Тестам
нужен Docker: они поднимают настоящие Postgres, RabbitMQ, Redis и MinIO —
шаблон опирается на `JSONB`, `SKIP LOCKED`, `ON CONFLICT` и подпись SigV4, и
зелёный прогон на SQLite не значил бы ничего. При изменении схемы дополнительно
выполняется локальный Alembic-цикл из `.agents/skills/pre-commit/SKILL.md`.

## Документация

| Где | Что |
| --- | --- |
| `AGENTS.md` | инварианты проекта одним экраном и указатель на остальное |
| `.agents/rules/` | правила по темам; таблица триггеров находится в `AGENTS.md` |
| `.agents/skills/new-module/SKILL.md` | как создаётся модуль |
| `.agents/skills/background-effect/SKILL.md` | чем делать побочный эффект: outbox, хук, задача, консьюмер |
| `.agents/skills/db-migration/SKILL.md` | как менять схему базы |
| `.agents/skills/pre-commit/SKILL.md` | что проверить перед коммитом, включая правила без автоматики |
| `src/app/modules/health/AGENTS.md` + локальный skill | liveness, readiness и dependency probes |
| `src/app/modules/storage/AGENTS.md` + локальный skill | двухфазная загрузка и S3 вне транзакции |
| [`../../AGENTS.md`](../../AGENTS.md) | рабочие области, context discovery и бюджеты |
| `docs/adr/` | почему приняты спорные решения |
| `.env.example` | каждая переменная с объяснением, зачем она и чем грозит |

Спорные решения вынесены в отдельные записи:

| ADR | Решение |
| --- | --- |
| [0001](docs/adr/0001-outbox-instead-of-publish-on-2xx.md) | публикация события не привязана к HTTP-статусу, а идёт через outbox |
| [0002](docs/adr/0002-keyset-pagination.md) | keyset-пагинация вместо `OFFSET` |
| [0003](docs/adr/0003-generic-crud.md) | обобщённый `CRUD` допустим — и чем он ограничен |
| [0004](docs/adr/0004-rfc-9457-problem-json.md) | все ошибки в формате RFC 9457 |
| [0005](docs/adr/0005-relay-takes-publish-as-an-argument.md) | релей получает публикацию аргументом, а не импортирует транспорт |
| [0006](docs/adr/0006-function-scoped-write-transaction.md) | `scope="function"` у пишущей транзакции |
| [0007](docs/adr/0007-event-without-subscribers-is-not-an-error.md) | событие без подписчиков — не ошибка |
| [0008](docs/adr/0008-single-worker-process.md) | вся фоновая работа в одном процессе |
