"""Шина доменных событий: запись в outbox, подписка, хуки после коммита.

Модуль сообщает о факте («заказ создан»), а не отдаёт команду («отправь
письмо»): отправитель не знает своих потребителей и не ждёт их. Благодаря
этому модули не импортируют друг друга и остаются заменяемыми по одному.

Здесь нет ни брокера, ни сети. `emit()` только кладёт строку в текущую
транзакцию; забирает её и публикует релей — отдельный процесс. Так «событие
отправлено» перестаёт зависеть от того, жив ли RabbitMQ в момент запроса.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar, Final, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context import actor_id, request_id
from app.kernel.db.session import AFTER_COMMIT_HOOKS, AfterCommitHook
from app.kernel.events.models import OutboxMessage

#: Обработчик события: `async def handler(event: EventType, session) -> None`.
#: Тип события у каждого подписчика свой, поэтому аргументы не уточняются —
#: соответствие «подписчик ↔ событие» проверяет реестр по декоратору.
Handler = TypeVar("Handler", bound=Callable[..., Awaitable[None]])

#: Атрибут, которым `subscribe` помечает функцию. Реестр читает его же —
#: имя не должно расходиться, поэтому оно объявлено один раз.
EVENTS_ATTR: Final = "__domain_events__"


class DomainEvent(BaseModel):
    """Факт, о котором модуль сообщает остальному приложению.

    Неизменяемое: событие описывает то, что уже произошло, и правка его полей
    после `emit()` означала бы, что в outbox уехало одно, а обработчику в
    памяти досталось другое.

    Наследник обязан объявить `topic` — стабильное имя факта, по которому
    сообщение маршрутизируется и восстанавливается в объект на стороне
    потребителя.
    """

    model_config = ConfigDict(frozen=True)

    topic: ClassVar[str]


def topic_of(event_type: type[DomainEvent]) -> str:
    """Вернуть топик класса события, либо поднять `TypeError`.

    Принимает класс события, возвращает непустую строку топика. Кидает
    `TypeError`, если топик не объявлен.

    Отдельная функция, а не обращение к `event_type.topic`: `topic` объявлен в
    базовом классе как `ClassVar` без значения, поэтому у события, забывшего
    его задать, простое чтение атрибута дало бы `AttributeError` где-то в
    середине сериализации — без единого намёка на то, что именно исправлять.
    """
    topic = getattr(event_type, "topic", None)
    if not isinstance(topic, str) or not topic:
        raise TypeError(
            f"{event_type.__qualname__} declares no topic: every DomainEvent subclass "
            f"must set a non-empty `topic: ClassVar[str]`, for example 'order.created'"
        )
    return topic


def emit(session: AsyncSession, event: DomainEvent) -> None:
    """Записать событие в outbox текущей транзакции.

    Принимает сессию открытой транзакции и событие, ничего не возвращает.
    Кидает `TypeError`, если у события не объявлен топик.

    Функция синхронная и без единого обращения к базе: только `session.add()`.
    Это не оптимизация, а условие корректности. Любой `await` внутри — это
    точка, где транзакция может задержаться или упасть по чужой причине, а
    смысл outbox ровно в том, что запись события стоит столько же, сколько
    запись самих данных, и разъехаться с ними не может.

    `request_id` и `actor_id` подмешиваются из контекста, а не передаются
    аргументом: иначе каждый вызывающий обязан был бы помнить про них, и
    первое же забытое место обрывало бы цепочку логов между сервисом и
    обработчиком события.
    """
    session.add(
        OutboxMessage(
            topic=topic_of(type(event)),
            # mode="json" обязателен: в JSONB нет ни datetime, ни UUID, ни
            # Decimal, а обычный model_dump оставил бы их объектами Python, и
            # падение случилось бы уже на вставке.
            payload=event.model_dump(mode="json"),
            headers=_current_headers(),
            # Время ставит Python, а не сервер: `now()` в Postgres одинаков
            # для всей транзакции, и порядок событий внутри неё пропал бы.
            occurred_at=datetime.now(tz=UTC),
        )
    )


def subscribe(*events: type[DomainEvent]) -> Callable[[Handler], Handler]:
    """Пометить функцию как обработчик перечисленных событий.

    Принимает классы событий, возвращает декоратор, который возвращает
    исходную функцию нетронутой. Кидает `ValueError`, если не передано ни
    одного события.

    Декоратор именно помечает, а не регистрирует: глобальный реестр,
    наполняемый импортом, зависел бы от того, кто какой модуль успел
    импортировать. Индексы строит `build_event_registry` из `MODULES` — то
    есть из единственного места, где состав приложения объявлен явно.
    """
    if not events:
        raise ValueError("subscribe() needs at least one event type")

    def decorate(handler: Handler) -> Handler:
        setattr(handler, EVENTS_ATTR, events)
        return handler

    return decorate


def subscribed_events(
    handler: Callable[..., Awaitable[None]],
) -> tuple[type[DomainEvent], ...] | None:
    """Вернуть события, объявленные декоратором `subscribe`.

    Принимает функцию, возвращает кортеж классов событий или `None`, если
    функция декоратором не помечена. `None`, а не пустой кортеж: «подписчик
    без декоратора» — ошибка конфигурации, и реестр обязан отличать её от
    осмысленного «событий нет».
    """
    declared: tuple[type[DomainEvent], ...] | None = getattr(handler, EVENTS_ATTR, None)
    return declared


def after_commit(session: AsyncSession, fn: AfterCommitHook) -> None:
    """Отложить корутину до момента после успешного коммита транзакции.

    Принимает сессию текущей транзакции и функцию без аргументов, ничего не
    возвращает. Выполняет хуки владелец транзакции (`get_uow`); откат
    транзакции отменяет и их.

    Никаких гарантий доставки: процесс, упавший между коммитом и хуком,
    потеряет его молча. Поэтому сюда кладут только то, потерю чего бизнес
    переживёт, — прогрев кеша, метрику, необязательное уведомление. Всё
    остальное идёт через `emit()`.

    Хранилище — `session.info`, а не событие SQLAlchemy `after_commit`:
    последнее синхронное, и `await` внутри него невозможен.
    """
    hooks: list[AfterCommitHook] = session.info.setdefault(AFTER_COMMIT_HOOKS, [])
    hooks.append(fn)


def _current_headers() -> dict[str, Any]:
    """Транспортные метаданные события из контекста операции.

    `actor_id` кладётся только когда он известен: `null` в каждом сообщении
    ничего не сообщает потребителю, но занимает место в его индексах.
    """
    headers: dict[str, Any] = {"request_id": request_id.get()}
    actor = actor_id.get()
    if actor is not None:
        headers["actor_id"] = str(actor)
    return headers
