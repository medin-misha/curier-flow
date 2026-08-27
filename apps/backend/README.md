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
- [Outbox на примере: заказ → уведомление в Telegram](#outbox-на-примере-заказ--уведомление-в-telegram)
- [Воркер: что в нём живёт и почему не в uvicorn](#воркер-что-в-нём-живёт-и-почему-не-в-uvicorn)
- [Команды](#команды)
- [Документация](#документация)

## Требования

| Что | Зачем |
| --- | --- |
| **Docker** и **docker compose** | PostgreSQL, RabbitMQ, Redis, MinIO; тесты поднимают свои контейнеры через testcontainers |
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
docker compose -f infra/docker-compose.apps.yml exec api alembic upgrade head
curl -s localhost:8000/health/ready
```

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
3. `make -C infra up` — поднимает PostgreSQL, RabbitMQ, Redis, MinIO, затем
   процессы `api` (порт 8000) и `worker`. Первый запуск собирает образы, это
   несколько минут; дальше — секунды;
4. Alembic внутри контейнера `api` накатывает схему базы в том же окружении;
5. проверка готовности.

Дальше можно потрогать шаблон руками:

```bash
curl -s localhost:8000/health/info   # {"name":...,"version":...,"revision":"8f4f401e3143"}
curl -s localhost:8000/files         # {"items":[],"next_cursor":null} — пустая keyset-страница
open http://localhost:8000/docs                    # Swagger (DEBUG=true)
open http://localhost:15672                        # RabbitMQ, guest/guest
open http://localhost:9001                         # консоль MinIO, minioadmin/minioadmin
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
  `import-linter` (правила слоёв), `pre-commit`, GitHub Actions;
- 400+ тестов на настоящих Postgres, RabbitMQ, Redis и MinIO через
  testcontainers, включая архитектурные проверки: «хендлер не ходит в базу»,
  «сервис не знает про HTTP», «модуль не коммитит», «каждый модуль в реестре».

**AI-native**

- запускайте backend-задачи через `codex --cd apps/backend`, а существующий
  модуль — через `codex --cd apps/backend/src/app/modules/<name>`;
- `AGENTS.md` содержит только обязательные инварианты и маршрутизацию;
- `.agents/rules/` хранит подробные backend-правила по типам изменений;
- `.agents/skills/` хранит backend-процессы: `new-module`,
  `background-effect`, `db-migration`, `pre-commit`;
- у сложного модуля есть короткий `AGENTS.md` и локальный skill с
  тематическими `references/`.

Полная схема областей запуска и контекстные бюджеты описаны в
[`../../docs/codex-context.md`](../../docs/codex-context.md).

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

Не пишите каркас руками — запустите `codex --cd apps/backend` и используйте
skill **`.agents/skills/new-module/SKILL.md`**.
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

## Outbox на примере: заказ → уведомление в Telegram

Задача: при создании заказа отправить сообщение в Telegram. Модуль `orders`
ничего не знает про Telegram, модуль `notifications` ничего не знает про
заказы.

### 1. Сервис заказа сообщает о факте

```python
# src/app/modules/orders/services.py
async def create_order(request: OrderCreate, *, session: AsyncSession) -> Order:
    """Создать заказ и сообщить об этом остальному приложению."""
    order = await CRUD.create(Order, request, session, owner_id=actor_id.get())
    emit(session, OrderCreated(order_id=order.id, total=order.total, owner_id=order.owner_id))
    return order
```

`emit()` не отправляет ничего. Он делает один `session.add()` — кладёт строку в
таблицу `outbox` **в ту же транзакцию**, в которой создаётся заказ. Ни сети, ни
`await`, ни брокера.

### 2. Подписчик реагирует

```python
# src/app/modules/notifications/events.py
# Это локальная проекция чужого топика, а не импорт из orders.
class OrderCreated(DomainEvent):
    topic: ClassVar[str] = "order.created"

    order_id: UUID
    total: Decimal
    owner_id: UUID


class OrderTelegramNotificationCreated(DomainEvent):
    topic: ClassVar[str] = "order.telegram_notification.created"

    chat_id: int
    order_id: UUID
    total: Decimal
```

```python
# src/app/modules/notifications/subscribers.py
@subscribe(OrderCreated)
async def prepare_telegram_notification(
    event: OrderCreated,
    session: AsyncSession,
) -> None:
    """Зафиксировать непотеряемое уведомление без внешнего I/O."""
    emit(
        session,
        OrderTelegramNotificationCreated(
            chat_id=notifications_settings.chat_id,
            order_id=event.order_id,
            total=event.total,
        ),
    )
```

```python
# src/app/modules/notifications/module.py
telegram_topology = TopologyDecl(
    exchange="domain.events",
    queue="telegram.notifications",
    routing_key=OrderTelegramNotificationCreated.topic,
    retry_ttl_ms=30_000,
)

notifications_module = Module(
    name="notifications",
    subscribers=(prepare_telegram_notification,),
    topology=(telegram_topology,),
)
```

Модуль `orders` не импортирует `notifications`, а `notifications` не импортирует
даже класс события `orders`: межмодульный контракт — стабильный topic и
локальная Pydantic-схема. Подписчик не вызывает Telegram в открытой
транзакции, а атомарно с `processed_messages` создаёт второй outbox-факт.
Durable очередь объявляется backend worker до запуска релея, а отдельный
Telegram service потребляет её без `ConsumerDecl` в backend.

Для личной доставки Admin должен заранее открыть бота и нажать `/start`:
одного корректного `telegram_id` недостаточно, чтобы бот начал диалог.
Notification payload и DLQ содержат PII, поэтому production-доступ к RabbitMQ
management и права bot-пользователя должны быть минимальными.

### 3. Что происходит между ними

```
POST /orders
   │
   ├─ транзакция запроса:  INSERT orders …
   │                       INSERT outbox (topic='order.created', payload={…})
   ├─ COMMIT ─────────────── либо есть и заказ, и событие, либо нет ни того, ни другого
   └─ 201 Created клиенту

   … в это время в процессе worker, раз в OUTBOX_RELAY_INTERVAL секунд …

   релей: SELECT … WHERE published_at IS NULL FOR UPDATE SKIP LOCKED
          publish → RabbitMQ (exchange domain.events, routing_key order.created)
          UPDATE outbox SET published_at = now()

   консьюмер: получил сообщение
              INSERT processed_messages (message_id)   ← в транзакции
              INSERT outbox (topic='order.telegram_notification.created', …)
              COMMIT → ack

   релей: publish order.telegram_notification.created → telegram.notifications
   внешний Telegram service: sendMessage → ACK
```

### Почему HTTP-статус в этой цепочке не участвует

Соблазнительный вариант — «ручка вернула 201, значит публикуем» — ломается на
каждом шаге:

- **Ответ не равен коммиту.** Между `return` из ручки и коммитом транзакции
  ещё может упасть отложенное ограничение или случиться дедлок. Публикация «по
  2xx» отправила бы уведомление о заказе, которого нет в базе.
- **Публикация не равна успеху.** Если RabbitMQ лежит, `publish` внутри
  запроса либо повесит клиента на таймауте, либо потеряет событие. Заказ при
  этом создан — и уведомление не уедет уже никогда.
- **Ручка — не единственный вход.** Тот же `create_order` вызывается из задачи,
  из консьюмера и из скрипта миграции данных. У них никакого HTTP-статуса нет,
  а событие обязано уехать так же.
- **Откат обязан уносить и событие.** Если транзакция откатилась, строка outbox
  исчезает вместе с заказом. Публиковать нечего — и это не требует ни одной
  строки кода.

Поэтому триггер — **успешный коммит**, а не ответ. Событие и данные становятся
видимыми одним `COMMIT`, а доставка — забота релея, который переживёт и падение
брокера, и перезапуск процесса.

Цена: доставка **at-least-once**. Релей может опубликовать сообщение и упасть
до того, как отметит строку; брокер может доставить его дважды. Поэтому
подписчик обязан быть идемпотентным, а отметка `processed_messages` стоит в той
же транзакции, что и его работа.

Внешний HTTP-вызов из subscriber transaction запрещён: его нельзя атомарно
связать с `processed_messages`, а блокировка базы будет ждать чужую сеть.
Непотеряемая интеграция создаёт второй outbox-факт, как в примере выше;
отдельный consumer вызывает Telegram и подтверждает AMQP-сообщение только
после ответа API. Окно «Telegram принял запрос, consumer умер до ACK» всё равно
оставляет допустимый для at-least-once доставки дубль.

### Если потерять не жалко

Для эффектов, потеря которых бизнесу безразлична — прогрев кеша, метрика,
необязательный пинг, — есть `after_commit`:

```python
after_commit(session, lambda: cache.warm(order.id))
```

Хук выполняется после успешного коммита и **никаких гарантий не даёт**: процесс,
упавший между коммитом и хуком, потеряет его молча. Правило выбора одно: если
на вопрос «а если этот эффект не случится?» ответ длиннее одного слова — нужен
`emit()`.

## Воркер: что в нём живёт и почему не в uvicorn

Контейнер `worker` из `infra/docker-compose.apps.yml` запускает
`python -m app.worker` — один процесс, в котором крутится вся фоновая работа:

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
| `make migrate` | `alembic upgrade head` |
| `make revision m="add orders"` | сгенерировать миграцию по моделям |

Команды выше выполняются из `apps/backend/`. Контейнеры запускаются только из
корня репозитория через `infra/`:

| Команда | Что делает |
| --- | --- |
| `make -C infra help` | показать команды управления стеком |
| `make -C infra up` | поднять весь стек |
| `make -C infra up-infra` | поднять только инфраструктуру |
| `make -C infra reboot-apps` | пересобрать и пересоздать `api` и `worker` |
| `make -C infra down` | остановить весь стек с сохранением данных |

`make check` и `make test` обязаны быть зелёными перед каждым коммитом. Тестам
нужен Docker: они поднимают настоящие Postgres, RabbitMQ, Redis и MinIO —
шаблон опирается на `JSONB`, `SKIP LOCKED`, `ON CONFLICT` и подпись SigV4, и
зелёный прогон на SQLite не значил бы ничего.

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
| `../../docs/codex-context.md` | как выбирать `codex --cd` и как устроен progressive disclosure |
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
