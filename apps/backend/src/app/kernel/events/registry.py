"""Индексы событий и подписчиков, собранные из манифестов модулей.

Потребителю сообщения нужны два ответа: «какому классу соответствует топик из
заголовка» и «кому отдать разобранное событие». Оба вычисляются один раз при
старте процесса из `MODULES` — того же списка, из которого собираются роутер,
задачи и топология брокера.

Сборка — явный вызов, а не побочный эффект импорта. Реестр, наполняемый на
импорте, зависит от того, какие модули кто-то успел загрузить, и «подписчик не
сработал» превращается в поиск недостающего `import`.
"""

from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from app.kernel.events.bus import DomainEvent, subscribed_events, topic_of
from app.kernel.registry import Module

#: Обработчик события. Точные типы аргументов у каждого свои, а реестр хранит
#: их вперемешку, поэтому здесь только общая часть контракта.
Subscriber = Callable[..., Awaitable[None]]


class EventRegistryError(Exception):
    """Ошибка конфигурации событий, обнаруженная при сборке реестра.

    Поднимается на старте процесса и роняет его намеренно: сервис, у которого
    часть подписчиков молча не подключилась, хуже упавшего — он выглядит
    работающим и теряет события до первого разбора инцидента.
    """


@dataclass(frozen=True, slots=True)
class EventRegistry:
    """Что процесс умеет разбирать и кому это отдавать."""

    #: Топик → класс события. Только те события, на которые кто-то подписан:
    #: разбирать сообщение, которое некому обработать, незачем.
    topics: Mapping[str, type[DomainEvent]]

    #: Класс события → подписчики в порядке объявления в `MODULES`.
    handlers: Mapping[type[DomainEvent], tuple[Subscriber, ...]]

    def event_for(self, topic: str) -> type[DomainEvent] | None:
        """Вернуть класс события по топику или `None`, если топик неизвестен.

        `None`, а не исключение: неизвестный топик — это чужое или устаревшее
        сообщение, и решать его судьбу (лог, DLQ, пропуск) обязан потребитель,
        который один знает, можно ли подтверждать доставку.
        """
        return self.topics.get(topic)

    def subscribers_for(self, event_type: type[DomainEvent]) -> tuple[Subscriber, ...]:
        """Вернуть подписчиков события; пустой кортеж, если их нет."""
        return self.handlers.get(event_type, ())


def build_event_registry(modules: Sequence[Module]) -> EventRegistry:
    """Построить индексы событий по манифестам модулей.

    Принимает реестр модулей, возвращает готовый `EventRegistry`. Кидает
    `EventRegistryError` на ошибках конфигурации и `TypeError` на событии без
    топика — всё это на старте процесса, а не при первом сообщении.
    """
    topics: dict[str, type[DomainEvent]] = {}
    handlers: dict[type[DomainEvent], list[Subscriber]] = defaultdict(list)

    for module in modules:
        for handler in module.subscribers:
            for event_type in _declared_events(module, handler):
                _claim_topic(topics, event_type)
                handlers[event_type].append(handler)

    return EventRegistry(
        topics=MappingProxyType(topics),
        handlers=MappingProxyType(
            {event_type: tuple(found) for event_type, found in handlers.items()}
        ),
    )


def _declared_events(module: Module, handler: Subscriber) -> tuple[type[DomainEvent], ...]:
    """События подписчика; непомеченная функция — ошибка конфигурации.

    Функция в `subscribers` без декоратора `@subscribe(...)` не сообщает, что
    именно слушает. Промолчать здесь означало бы получить модуль, который
    подписан на всё и не получает ничего.
    """
    declared = subscribed_events(handler)
    if declared is None:
        raise EventRegistryError(
            f"Module '{module.name}' lists subscriber '{_name_of(handler)}' "
            f"that is not decorated with @subscribe(...): the registry cannot tell "
            f"which events it listens to."
        )
    return declared


def _claim_topic(topics: dict[str, type[DomainEvent]], event_type: type[DomainEvent]) -> None:
    """Закрепить топик за классом события; чужой топик — ошибка конфигурации.

    Топик определяет схему полезной нагрузки: по нему потребитель выбирает
    класс, в который разбирает сообщение. Два класса на один топик означают,
    что разбор зависит от порядка обхода `MODULES`, — такое лучше уронить на
    старте.
    """
    topic = topic_of(event_type)
    claimed = topics.setdefault(topic, event_type)
    if claimed is not event_type:
        raise EventRegistryError(
            f"Topic '{topic}' is claimed by two event classes: "
            f"{claimed.__qualname__} and {event_type.__qualname__}. "
            f"A topic identifies the payload schema, so it must be unique."
        )


def _name_of(handler: Subscriber) -> str:
    """Имя обработчика для сообщения об ошибке; работает и на не-функциях."""
    module = getattr(handler, "__module__", "?")
    name = getattr(handler, "__qualname__", repr(handler))
    return f"{module}.{name}"
