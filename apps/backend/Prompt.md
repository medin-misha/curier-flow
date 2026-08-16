# Задача: собрать production-ready шаблон backend-сервиса

Ты — оркестратор. Ты **не пишешь код сам**. Ты декомпозируешь работу на этапы, на каждый этап
запускаешь отдельного суб-агента, принимаешь его работу, проверяешь и делаешь коммит.

---

## 0. Правила работы оркестратора

1. **Один этап — один суб-агент.** Этапы выполняются строго последовательно. Не запускай
   несколько суб-агентов параллельно: этапы зависят друг от друга по контрактам.
2. **Суб-агент не видит твой контекст.** В задание каждому суб-агенту копируй целиком:
   - раздел «Общие инварианты» (Файл "Общие инвайты.md"),
   - раздел «Контракты API» (Файл "Контракты API.md") — только те подразделы, что нужны его этапу,
   - полный текст его этапа из §4.
     Не пиши «см. выше» — суб-агент этого не увидит.
3. **Приёмка.** После отчёта суб-агента ты лично:
   - запускаешь `make check` (линт + типы + import-linter) и `make test`;
   - открываешь ключевые созданные файлы и сверяешь сигнатуры с §2;
   - если критерии готовности этапа не выполнены — возвращаешь суб-агенту список
     конкретных расхождений и запускаешь доработку. Не чини сам.
4. **Коммит после каждого этапа.** Формат — Conventional Commits, одна строка заголовка,
   в теле — что вошло в этап. Пример:
   ```
   feat(kernel): база данных, конфиг, ошибки, контекст запроса

   - Base + миксины, session factory, get_uow/get_ro_session
   - CRUD с whitelist-патчем, keyset-пагинация
   - иерархия AppError, contextvars запроса
   ```

   Коммит делаешь ты, не суб-агент. Перед коммитом — `make check && make test` должны быть зелёными.
5. **Ничего не выдумывай сверх задания.** Если в этапе не сказано про фичу — её не делаем.
   Если контракт из §2 кажется неправильным — остановись и спроси меня, не переписывай молча.
6. **Никаких заглушек в мёрже.** `TODO`, `pass  # implement later`, замоканные функции в
   коммит не попадают. Этап либо готов, либо не коммитится.

---

## 1. Общие инварианты (копировать каждому суб-агенту)

Это шаблон backend-сервиса на **FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL**.
Цель шаблона: `git clone` → заполнить `.env` → написать свой модуль → запустить.
Пользователь шаблона пишет только бизнес-модули, вся инфраструктура уже есть.

**Стек:** Python 3.12+, uv, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, Pydantic v2 +
pydantic-settings, aio-pika, TaskIQ, aiobotocore/miniopy-async для S3, structlog,
pytest + pytest-asyncio + testcontainers.

**Раскладка проекта:**

```
pyproject.toml
Makefile
docker-compose.yml
.env.example
alembic/
  env.py
  versions/
src/app/
  main.py                 # HTTP entrypoint (uvicorn)
  worker.py               # TaskIQ + консьюмеры RabbitMQ + релей outbox
  api/
    router.py             # сборка главного роутера из реестра модулей
    errors.py             # exception handlers → RFC 9457
    middleware.py         # ТОЛЬКО транспорт: request-id, тайминг, логи
    deps.py               # общие зависимости (пагинация, идемпотентность)
  kernel/                 # фундамент, не зависит ни от чего внутри app
    config.py
    context.py
    errors.py
    pagination.py
    registry.py           # Module, реестр
    db/
      base.py  mixins.py  session.py  crud.py
    events/
      bus.py  models.py  outbox.py  registry.py
    security/
      passwords.py  tokens.py
  platform/               # адаптеры к внешнему миру, зависят только от kernel
    rabbitmq.py  taskiq.py  s3.py
  modules/
    __init__.py           # MODULES: список манифестов
    health/
    storage/
tests/
.claude/
  CLAUDE.md
  skills/new-module/
```

**Правила зависимостей (проверяются import-linter, нарушение = провал этапа):**

```
api → modules → platform → kernel
```

- `kernel` не импортирует `platform`, `modules`, `api`.
- `platform` не импортирует `modules`, `api`.
- модули **не импортируют друг друга** — только через доменные события.
- `alembic/env.py` зависит от `kernel` и `modules`, но не от `api`.

**Правила слоёв внутри модуля:**

- `handlers.py` — только HTTP: разбор запроса, вызов сервиса, формирование ответа.
  **Запрещено:** импорт `CRUD`, вызов `session.commit()`, обращение к S3/RabbitMQ напрямую.
- `services.py` — бизнес-логика. Единственное место, где вызывается `CRUD` и `emit()`.
- `models/` — SQLAlchemy-модели.
- `schemas/` — `requests.py`, `responses.py`, опционально `commands.py`.
- `subscribers.py` — обработчики доменных событий (опционально).
- `tasks.py` — задачи TaskIQ (опционально).
- `module.py` — манифест `Module`.
- `.claude/CLAUDE.md` — контекст модуля.

**Транзакции:**

- Одна транзакция на запрос. Коммит выполняет зависимость `get_uow` при выходе из блока,
  хендлер `commit()` не вызывает никогда.
- `async_sessionmaker(expire_on_commit=False)` — обязательно, иначе сериализация ответа
  упадёт на lazy-load после коммита.
- **Внутри транзакции запрещён внешний I/O** (S3, HTTP, RabbitMQ). Только БД.
  Походы наружу — до открытия транзакции, после коммита, или через outbox.
- Для чистого чтения — `get_ro_session` без `begin()`.

**События:**

- Побочные эффекты **никогда** не привязываются к HTTP-статусу ответа. Триггер — commit транзакции.
- Событие, потеря которого заметна бизнесу → `emit()` в ту же транзакцию (outbox).
- Событие, потерю которого можно пережить (прогрев кеша, метрика) → хук `after_commit` в памяти.
- Доставка — at-least-once. Все потребители обязаны быть идемпотентны.

**Разграничение RabbitMQ и TaskIQ:**

- **TaskIQ** — исполнение нашей работы: отложенные и периодические задачи, ретраи, релей outbox.
- **RabbitMQ (aio-pika)** — транспорт сообщений во внешние сервисы, которые мы не контролируем,
  и приём сообщений от них.
- Оба живут только в процессе `worker.py`, никогда в процессе uvicorn.

**Стиль кода:**

- Полная типизация, `mypy --strict` для `kernel` и `platform`.
- Ранний возврат вместо вложенных условий.
- Явная передача зависимостей аргументами; глобальные синглтоны — только для пула соединений.
- Без абстракций «на будущее»: интерфейс заводится, когда есть вторая реализация.
- Докстринги на публичных функциях `kernel` и `platform`, объясняющие **почему**, а не **что**.
- Комментарии в коде и докстринги — на русском. Имена, сообщения об ошибках, логи — на английском.

---

## 2. Контракты API (нормативные, менять нельзя)

### 2.1 `kernel/context.py`

```python
request_id: ContextVar[str]              # default "-"
actor_id: ContextVar[UUID | None]        # default None
```

### 2.2 `kernel/errors.py`

```python
class AppError(Exception):
    code: ClassVar[str]          # machine-readable, kebab-case
    status: ClassVar[int]
    title: ClassVar[str]
    def __init__(self, detail: str | None = None, **extra: Any) -> None: ...

class NotFound(AppError):          # 404
class Conflict(AppError):          # 409
class ValidationFailed(AppError):  # 422
class PermissionDenied(AppError):  # 403
class Unauthorized(AppError):      # 401
class RateLimited(AppError):       # 429
class DependencyUnavailable(AppError):  # 503
```

Доменные ошибки модулей наследуются от них. HTTP-исключения FastAPI в `services.py` запрещены.

### 2.3 `kernel/db/session.py`

```python
engine: AsyncEngine
session_factory: async_sessionmaker[AsyncSession]   # expire_on_commit=False

async def get_uow() -> AsyncIterator[AsyncSession]:
    """Пишущая транзакция на запрос. Коммит при штатном выходе, откат при исключении."""

async def get_ro_session() -> AsyncIterator[AsyncSession]:
    """Сессия только для чтения, без открытия транзакции."""
```

### 2.4 `kernel/db/base.py`, `mixins.py`

```python
class Base(DeclarativeBase):
    __patchable__: ClassVar[frozenset[str]] = frozenset()

class UUIDPkMixin:      # id: Mapped[UUID], primary_key, default=uuid7
class TimestampMixin:   # created_at, updated_at (server_default=now(), onupdate)
class SoftDeleteMixin:  # deleted_at: Mapped[datetime | None]
```

### 2.5 `kernel/db/crud.py`

```python
class CRUD:
    @staticmethod
    async def create(model: type[T], dto: BaseModel, session: AsyncSession, **overrides: Any) -> T:
        """dto.model_dump() + overrides. Делает flush(), чтобы был доступен id."""

    @staticmethod
    async def get(model: type[T], pk: Any, session: AsyncSession) -> T | None: ...

    @staticmethod
    async def get_or_404(model: type[T], pk: Any, session: AsyncSession) -> T:
        """Кидает NotFound с именем модели в detail."""

    @staticmethod
    async def update(obj: T, patch: BaseModel, session: AsyncSession, *,
                     allowed: frozenset[str] | None = None) -> T:
        """patch.model_dump(exclude_unset=True). allowed по умолчанию берётся из
        type(obj).__patchable__. Поля вне allowed → Conflict, НЕ молчаливый фильтр."""

    @staticmethod
    async def delete(obj: T, session: AsyncSession) -> None: ...

    @staticmethod
    async def list_page(model: type[T], session: AsyncSession, *,
                        page: PageParams, where: Sequence[Any] = ()) -> Page[T]: ...
```

### 2.6 `kernel/pagination.py`

Keyset-пагинация. `OFFSET` в шаблоне не используется нигде.

```python
class PageParams(BaseModel):
    cursor: str | None = None      # base64 от (created_at, id)
    limit: int = Field(50, ge=1, le=200)

class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
```

Условие выборки: `WHERE (created_at, id) < (:ts, :id) ORDER BY created_at DESC, id DESC LIMIT n`.
Составной индекс `(created_at DESC, id DESC)` обязателен на каждой пагинируемой таблице.

### 2.7 Схемы Pydantic

```python
class BaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")   # лишние поля → 422, не молчаливый выброс

class BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

В `CreateSchema` попадает **только то, что клиент вправе задать**. Всё, что выводит сервер
(`user_id` из токена, `status`, `created_by`), передаётся через `**overrides` в `CRUD.create`.

### 2.8 `kernel/events/bus.py`

```python
class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    topic: ClassVar[str]           # напр. "order.created"

def emit(session: AsyncSession, event: DomainEvent) -> None:
    """Синхронно, без I/O. Пишет строку в outbox в текущую транзакцию.
    Автоматически подмешивает request_id и actor_id из contextvars в headers."""

def subscribe(*events: type[DomainEvent]) -> Callable[[Handler], Handler]:
    """Регистрирует обработчик события в реестре подписчиков."""

def after_commit(session: AsyncSession, fn: Callable[[], Awaitable[None]]) -> None:
    """Хук в памяти для неважных эффектов. Без гарантий доставки."""
```

Сигнатура подписчика: `async def handler(event: EventType, session: AsyncSession) -> None`.

### 2.9 `kernel/events/models.py`

```python
class OutboxMessage(Base, UUIDPkMixin):
    __tablename__ = "outbox"
    topic: Mapped[str]              # index
    payload: Mapped[dict]           # JSONB
    headers: Mapped[dict]           # JSONB
    occurred_at: Mapped[datetime]
    published_at: Mapped[datetime | None]   # partial index WHERE published_at IS NULL
    attempts: Mapped[int]
    last_error: Mapped[str | None]

class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    message_id: Mapped[UUID]        # PK
    processed_at: Mapped[datetime]
```

### 2.10 `kernel/registry.py`

```python
@dataclass(frozen=True, slots=True)
class Module:
    name: str
    router: APIRouter | None = None
    prefix: str | None = None                       # по умолчанию f"/{name}"
    settings: type[BaseSettings] | None = None      # свой env_prefix
    models: str | None = None                       # import path пакета моделей
    subscribers: Sequence[Callable[..., Awaitable[None]]] = ()
    tasks: Sequence[Callable[..., Awaitable[Any]]] = ()
    consumers: Sequence[ConsumerDecl] = ()
    topology: Sequence[TopologyDecl] = ()
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None
```

Единственный реестр — `MODULES: Final[tuple[Module, ...]]` в `src/app/modules/__init__.py`.
Из него собираются: главный роутер, lifespan (через `AsyncExitStack`), метаданные Alembic,
подписчики, расписание TaskIQ, топология RabbitMQ. Автодискавери по ФС не делать.

### 2.11 Формат ошибок — RFC 9457

`Content-Type: application/problem+json`

```json
{
  "type": "https://errors.local/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Order 018f... does not exist",
  "instance": "/orders/018f...",
  "request_id": "01JB3K..."
}
```

`RequestValidationError` от FastAPI перехватывается и приводится к тому же формату
(`status: 422`, поле `errors` со списком нарушений). Голых `{"detail": "..."}` в API быть не должно.

---

## 3. Как формулировать задание суб-агенту

Шаблон:

```
Ты работаешь над одним этапом сборки backend-шаблона.

[ § 1 Общие инварианты — целиком ]
[ § 2 Контракты, относящиеся к этапу — целиком ]
[ Текст этапа из § 4 ]

Правила:
- Делай ровно то, что описано в этапе. Файлы за пределами списка не трогай.
- Контракты из §2 — нормативные. Расходиться с ними нельзя. Если контракт мешает —
  останови работу и опиши проблему в отчёте, не переписывай его сам.
- Перед завершением запусти `make check` и `make test`, добейся зелёного.
- Не делай git commit. Коммит сделает оркестратор.
- В отчёте: список созданных/изменённых файлов, самопроверка по каждому пункту
  критериев готовности, список принятых решений, которые не были заданы явно.
```

---

## 4. Этапы

### Этап 1 — Каркас репозитория и инструменты контроля

**Суб-агент 1.** Цель — сделать так, чтобы правила архитектуры проверялись машиной с самого
начала, а не после того, как их нарушат.

Создать:

- `pyproject.toml` — uv, все зависимости стека, группы `dev`/`test`.
- Конфиг `ruff` (включая `flake8-tidy-imports.banned-api`), `mypy` (`strict` для
  `app.kernel.*` и `app.platform.*`), `pytest`, `coverage`.
- `.importlinter` (или секция в `pyproject.toml`) с контрактами:
  - `layers`: `app.api` > `app.modules` > `app.platform` > `app.kernel`;
  - `independence` для пакетов внутри `app.modules`.
- `Makefile`: `install`, `check` (ruff + mypy + lint-imports), `test`, `up`, `down`,
  `migrate`, `revision`, `run`, `worker`.
- `docker-compose.yml`: postgres:16, rabbitmq:3-management, minio — с healthcheck'ами.
- `.env.example` с исчерпывающим списком переменных и комментариями.
- `.gitignore`, `.dockerignore`, `pre-commit` конфиг (ruff + mypy + lint-imports).
- `Dockerfile` (multi-stage, uv, отдельные команды запуска api и worker).
- CI-workflow GitHub Actions: `make check`, `make test`, `alembic check`.
- Пустые пакеты со всеми `__init__.py` по раскладке из §1.

**Критерии готовности:**

- `uv sync` отрабатывает без ошибок.
- `make check` зелёный на пустом дереве.
- `lint-imports` действительно падает, если временно добавить импорт `app.api` в `app.kernel`
  (проверить руками, потом откатить) — приложить вывод в отчёт.
- `docker compose up -d` поднимает три сервиса, все healthy.

---

### Этап 2 — kernel: конфиг, контекст, ошибки, БД, CRUD, пагинация

**Суб-агент 2.** Контракты §2.1–2.7.

Создать:

- `kernel/config.py` — только общие настройки (DSN, лог-левел, окружение, версия).
  Настройки модулей здесь **не появляются**.
- `kernel/context.py` — contextvars.
- `kernel/errors.py` — иерархия `AppError`. Без единого упоминания HTTP-фреймворка.
- `kernel/db/base.py`, `mixins.py`, `session.py`, `crud.py`.
- `kernel/pagination.py` — кодирование/декодирование курсора, `PageParams`, `Page`.
- Тесты на `CRUD.update` (whitelist, `exclude_unset`, `Conflict` на запрещённое поле),
  на кодек курсора, на поведение `get_uow` при исключении.

**Критерии готовности:**

- `mypy --strict src/app/kernel` без ошибок.
- Есть тест, доказывающий, что `CRUD.update` **падает**, а не фильтрует молча.
- Есть тест, доказывающий откат транзакции при исключении внутри `get_uow`.
- `expire_on_commit=False` выставлен, есть тест на чтение атрибута объекта после коммита.
- Ни один файл `kernel` не импортирует `fastapi`.

---

### Этап 3 — Реестр модулей, сборка приложения, обработка ошибок, middleware, Alembic

**Суб-агент 3.** Контракты §2.10, §2.11.

Создать:

- `kernel/registry.py` — `Module`, `ConsumerDecl`, `TopologyDecl`, функции сборки:
  `build_router(modules)`, `build_lifespan(modules)` (через `AsyncExitStack`),
  `iter_model_packages(modules)`.
- `src/app/modules/__init__.py` — пустой `MODULES` (заполняется в следующих этапах).
- `api/middleware.py` — request-id (читает `X-Request-ID` или генерит), запись в contextvar,
  возврат в заголовке ответа, тайминг, структурный лог запроса через structlog.
  Больше в middleware **ничего**.
- `api/errors.py` — хендлеры `AppError`, `RequestValidationError`, необработанного
  `Exception` → RFC 9457. `request_id` в теле ответа обязателен.
- `api/router.py`, `api/deps.py`.
- `main.py` — сборка FastAPI: lifespan из реестра, middleware, хендлеры ошибок, роутер.
- `alembic/env.py` — импорт пакетов моделей из `MODULES` (не ручной список!),
  `target_metadata = Base.metadata`, `compare_type=True`, `compare_server_default=True`,
  async-движок.
- Тест полноты реестра: каждая директория в `src/app/modules` с файлом `module.py`
  присутствует в `MODULES`.

**Критерии готовности:**

- Приложение стартует с пустым `MODULES`, `/docs` открывается.
- Любая доменная ошибка отдаётся как `application/problem+json` с `request_id`.
- 422 от FastAPI приведён к тому же формату.
- `X-Request-ID` проходит насквозь: заголовок запроса → лог → заголовок ответа.
- Тест полноты реестра падает, если добавить директорию модуля и не внести её в `MODULES`
  (проверить руками, приложить вывод).

---

### Этап 4 — Доменные события и transactional outbox

**Суб-агент 4.** Контракты §2.8, §2.9. Это ядро всей механики побочных эффектов.

Создать:

- `kernel/events/models.py` — `OutboxMessage`, `ProcessedMessage`.
- `kernel/events/bus.py` — `DomainEvent`, `emit`, `subscribe`, `after_commit`.
- `kernel/events/registry.py` — маппинг «топик → класс события» и «событие → подписчики»,
  наполняется из `MODULES` при старте. Неизвестный топик при потреблении → лог + отправка в DLQ,
  не падение воркера.
- Alembic-миграцию на обе таблицы, с partial index `WHERE published_at IS NULL`.
- Тесты:
  - `emit()` не делает I/O и добавляет ровно одну строку в текущую транзакцию;
  - откат транзакции откатывает и событие (главный тест всей затеи);
  - `headers` содержат `request_id` из contextvar;
  - при исключении в `after_commit`-хуке основной ответ не ломается.

**Критерии готовности:**

- `emit()` не является корутиной и не обращается к сети.
- Есть тест: исключение после `emit()` внутри `get_uow` → в таблице `outbox` пусто.
- Есть тест: успешный коммит → ровно одна строка в `outbox` с `published_at IS NULL`.
- `kernel/events` не импортирует `platform` (публикацией занимается релей на этапе 6).

---

### Этап 5 — platform: RabbitMQ, TaskIQ, S3, процесс воркера

**Суб-агент 5.**

Создать:

- `platform/rabbitmq.py` — пул соединений aio-pika, декларация топологии из
  `TopologyDecl` (exchange, queue, binding, DLQ + retry-exchange с TTL), `publish()`,
  запуск консьюмеров из `ConsumerDecl`. Publisher confirms включены.
- `platform/taskiq.py` — брокер `AioPikaBroker` + result backend (Redis или Postgres —
  выбери и обоснуй в отчёте), `TaskiqScheduler`, регистрация задач из `MODULES`.
- `platform/s3.py` — клиент, `presigned_put`, `presigned_get`, `head_object`, `delete_object`,
  `list_prefix`. Никакой логики бизнес-уровня.
- `worker.py` — единая точка входа: TaskIQ worker + scheduler + консьюмеры RabbitMQ + релей
  outbox. Корректный graceful shutdown по SIGTERM (дождаться текущих сообщений).
- Хелпер идемпотентного потребления: обёртка, которая в транзакции обработчика делает
  `INSERT INTO processed_messages ... ON CONFLICT DO NOTHING` и пропускает уже обработанное.

**Критерии готовности:**

- `mypy --strict src/app/platform` без ошибок.
- Топология объявляется декларативно из манифестов, а не императивно при старте.
- Есть тест на testcontainers: публикация → потребление → повторная доставка того же
  `message_id` не приводит к повторной обработке.
- `worker.py` по SIGTERM завершается за отведённый таймаут без потери in-flight сообщений.
- Ни один импорт `platform` не встречается в процессе `main.py` (проверить import-linter'ом
  или тестом).

---

### Этап 6 — Релей outbox и доставка подписчикам

**Суб-агент 6.**

Создать:

- `kernel/events/outbox.py` — периодическая задача релея:
  - выборка `WHERE published_at IS NULL ORDER BY occurred_at LIMIT N FOR UPDATE SKIP LOCKED`;
  - публикация в RabbitMQ с `message_id = OutboxMessage.id` и переносом `headers`;
  - проставление `published_at`;
  - при ошибке — `attempts += 1`, `last_error`, экспоненциальная отсрочка;
  - после N неудач — перенос в DLQ и метрика.
- Консьюмер, который получает событие из очереди, находит подписчиков в реестре и вызывает их
  внутри `get_uow`-подобной транзакции с защитой `ProcessedMessage`.
- Задача очистки `outbox` от опубликованных строк старше N дней.

**Критерии готовности:**

- Интеграционный тест (testcontainers, реальные Postgres + RabbitMQ):
  сервис вызван → релей опубликовал → подписчик отработал ровно один раз.
- Тест: два релея, запущенные параллельно, не публикуют одно сообщение дважды
  (проверка `SKIP LOCKED`).
- Тест: недоступный брокер → строки остаются в `outbox`, `attempts` растёт, после
  восстановления брокера всё уезжает.
- Релей не блокирует таблицу для пишущих транзакций (проверить, что запись в `outbox`
  из параллельной сессии не ждёт).

---

### Этап 7 — Модуль `health`

**Суб-агент 7.** Первый живой модуль. Он же — эталон для скилла генерации модулей.

Создать `src/app/modules/health/` с полным набором файлов по §1, включая `.claude/CLAUDE.md`.

- `GET /health/live` — процесс жив, event loop не заблокирован. **Никаких походов в БД.**
- `GET /health/ready` — пул БД отвечает, брокер подключен, S3 доступен. Возвращает 503 и
  детализацию по каждой зависимости, если что-то лежит.
- `GET /health/info` — версия приложения, окружение, ревизия Alembic.
- Внести модуль в `MODULES`.

**Критерии готовности:**

- В `docker-compose` healthcheck API настроен на `/health/live`, а не на `/health/ready`.
- В `.claude/CLAUDE.md` модуля явно объяснено, чем live отличается от ready и почему
  их нельзя путать (liveness роняет контейнер, readiness только выводит из балансировки).
- Тест: при остановленном Postgres `/health/live` → 200, `/health/ready` → 503.

---

### Этап 8 — Модуль `storage`

**Суб-агент 8.** Двухфазная загрузка, файл не проходит через backend.

Модель `File`: `id`, `bucket`, `key`, `original_name`, `content_type`, `size`, `etag`,
`status` (`pending` / `ready` / `deleting`), `owner_id`, таймстемпы.

Эндпоинты:

- `POST /files/upload-url` — создаёт строку `status=pending`, возвращает presigned PUT.
  Транзакция коммитится **до** того, как клиент начнёт лить. Никакого S3-вызова внутри
  транзакции (presigned URL считается локально).
- `POST /files/{id}/confirm` — обязательный `head_object`: файл существует, размер и
  content-type в допустимых пределах, `etag` совпадает. Только после проверки `status=ready`
  и `emit(FileConfirmed)`. Если объекта нет — 404, если не прошёл валидацию — удалить объект и 422.
- `GET /files/{id}` — метаданные + presigned GET.
- `GET /files` — keyset-пагинация.
- `DELETE /files/{id}` — `status=deleting`, физическое удаление отложено в задачу.

Задачи:

- Сборщик сирот: `pending` старше TTL → удалить объект (если есть) и строку.
- Реальное удаление `deleting` → `delete_object` → удалить строку.

**Критерии готовности:**

- Ни одного вызова S3 внутри открытой транзакции — проверено тестом или явной инспекцией кода.
- Тест: `confirm` без реально загруженного объекта → 404, строка остаётся `pending`.
- Тест: `confirm` с превышением размера → 422, объект удалён из бакета.
- Тест: клиент «пропал» после получения URL → сборщик сирот убирает строку и объект.
- Тест: `FileConfirmed` попал в `outbox` в той же транзакции, что и смена статуса.
- В `.claude/CLAUDE.md` модуля описан жизненный цикл файла и запрет на проксирование
  файлов через backend.

---

### Этап 9 — Идемпотентность, безопасность, общие зависимости

**Суб-агент 9.**

- `kernel/security/passwords.py` — argon2/bcrypt хеширование.
- `kernel/security/tokens.py` — JWT: выпуск, проверка, refresh. Без модуля авторизации,
  только утилиты.
- `api/deps.py`:
  - `PageParams` как зависимость;
  - `Idempotency-Key`: таблица `idempotency_keys(key PK, request_hash, status, response_body, created_at)`, запись в транзакции запроса; повтор с тем же ключом и тем же телом →
    сохранённый ответ; тот же ключ с другим телом → 409;
  - `get_actor` — заготовка извлечения `actor_id` из токена в contextvar.
- Миграция на `idempotency_keys` + задача очистки просроченных ключей.

**Критерии готовности:**

- Тест: два одинаковых POST с одним `Idempotency-Key` → одна созданная сущность,
  второй ответ идентичен первому.
- Тест: тот же ключ с другим телом → 409.
- Тест: ключ сохраняется в той же транзакции, что и данные (откат откатывает и ключ).
- В `.claude/CLAUDE.md` объяснено, почему при at-least-once доставке идемпотентность
  на записи обязательна.

---

### Этап 10 — Тестовая обвязка и жёсткие проверки правил

**Суб-агент 10.** Здесь «правила» превращаются в «контракт».

- `tests/conftest.py` — testcontainers для Postgres, RabbitMQ, MinIO (session scope),
  миграции применяются один раз, каждый тест — во вложенной транзакции с откатом.
  SQLite не использовать ни при каких условиях (нужны JSONB, SKIP LOCKED, ON CONFLICT).
- Фабрика тестового приложения с подменой зависимостей.
- Архитектурные тесты (AST или grep-based, падают с внятным сообщением):
  - `session.commit()` не встречается в `src/app/modules/**`;
  - `CRUD` не импортируется в `**/handlers.py`;
  - `HTTPException` не встречается в `**/services.py`;
  - каждый пакет в `modules/` есть в `MODULES`;
  - каждый модуль имеет `.claude/CLAUDE.md`.
- Тест миграций в CI: пустая БД → `alembic upgrade head` → `alembic check` (нет
  несгенерированных изменений) → `alembic downgrade base`.
- Замер покрытия, порог для `kernel` — не ниже 85%.

**Критерии готовности:**

- Каждый архитектурный тест продемонстрирован в отчёте: сначала показан падающим на
  намеренном нарушении, потом зелёным после отката нарушения.
- `make test` проходит на чистой машине только с установленным Docker.
- `alembic check` в CI действительно ловит забытую миграцию.

---

### Этап 11 — Документация и скилл генерации модулей

**Суб-агент 11.** Именно это делает шаблон AI-native.

- `.claude/CLAUDE.md` корня: карта проекта, правила слоёв, правила транзакций, правило
  выбора «outbox или after_commit», разграничение TaskIQ/RabbitMQ, чек-лист перед коммитом,
  команды `make`. Пиши в форме проверяемых утверждений, не абстрактных принципов.
- `.claude/skills/new-module/SKILL.md` — скилл создания модуля. Генерирует полную структуру:
  `handlers.py`, `services.py`, `models/`, `schemas/{requests,responses}.py`, `module.py`,
  `.claude/CLAUDE.md`, заготовки тестов; вносит модуль в `MODULES`; напоминает про миграцию.
- `README.md`: быстрый старт (5 команд), схема архитектуры, объяснение outbox на примере
  «создал заказ → уведомление в Telegram», как добавить модуль, как запускать воркер.
- `docs/adr/` — краткие ADR по спорным решениям: почему не «2xx → publish», почему keyset,
  почему generic CRUD допустим и чем ограничен, почему RFC 9457.
- Демо: пример из README должен быть воспроизводим за 5 минут на чистой машине.

**Критерии готовности:**

- Пройди путь пользователя вживую: склонировать в чистую директорию, `cp .env.example .env`,
  `make up`, `make migrate`, вызвать скилл, создать модуль `demo` с одним CRUD-ресурсом и
  одним событием, `make run` + `make worker`, дёрнуть эндпоинт, увидеть событие у подписчика.
  Приложить в отчёт лог этого прохода.
- Каждое правило в корневом `CLAUDE.md` сопровождается указанием, какая команда его проверяет.
  Правило, которое ничем не проверяется, либо получает проверку, либо удаляется.

---

## 5. Определение готовности всего шаблона

Шаблон считается готовым, когда одновременно верно:

1. На чистой машине с Docker: `git clone` → `cp .env.example .env` → `make up` →
   `make migrate` → `make run` даёт работающий API с открытым `/docs`.
2. `make check` и `make test` зелёные; CI зелёный.
3. Создание нового модуля через скилл требует правок **только** внутри директории модуля
   плюс одна строка в `MODULES`. Ни `config.py`, ни `lifecycle`, ни `alembic/env.py`,
   ни `router.py` руками не трогаются.
4. Побочный эффект «после успешной записи отправить сообщение в очередь» реализуется одной
   строкой `emit(...)` в сервисе и одной функцией-подписчиком. HTTP-статус в этой цепочке
   не участвует нигде.
5. Падение RabbitMQ не приводит к потере событий: после восстановления всё доезжает.
6. Нарушение любого архитектурного правила ловится командой, а не ревьюером.
7. В коде нет `TODO`, закомментированного кода и мёртвых абстракций.

---

## 6. Старт

Начни с этапа 1. Перед запуском первого суб-агента выведи мне план: список этапов,
что войдёт в каждый коммит, и какие решения тебе пока не ясны. Дождись моего «поехали».
