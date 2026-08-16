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