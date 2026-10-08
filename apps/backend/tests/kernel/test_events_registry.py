"""Реестр событий: индексы по манифестам и ошибки конфигурации на старте."""

from typing import ClassVar

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.events.bus import DomainEvent, subscribe, subscribed_events
from app.kernel.events.registry import EventRegistryError, build_event_registry
from app.kernel.registry import Module


class OrderCreated(DomainEvent):
    """Событие, на которое подписываются в тестах ниже."""

    topic: ClassVar[str] = "order.created"

    number: int


class OrderShipped(DomainEvent):
    """Второе событие: нужно, чтобы проверить подписку на несколько сразу."""

    topic: ClassVar[str] = "order.shipped"

    number: int


class OrderCreatedTwin(DomainEvent):
    """Чужой класс, занявший тот же топик, что и `OrderCreated`."""

    topic: ClassVar[str] = "order.created"


class Untopiced(DomainEvent):
    """Событие без топика: ошибка автора, а не конфигурации."""


@subscribe(OrderCreated)
async def notify(_event: OrderCreated, _session: AsyncSession) -> None:
    """Подписчик первого модуля."""


@subscribe(OrderCreated, OrderShipped)
async def audit(_event: DomainEvent, _session: AsyncSession) -> None:
    """Подписчик, слушающий оба события."""


@subscribe(OrderCreatedTwin)
async def handle_twin(_event: OrderCreatedTwin, _session: AsyncSession) -> None:
    """Подписчик события-двойника."""


@subscribe(Untopiced)
async def handle_untopiced(_event: Untopiced, _session: AsyncSession) -> None:
    """Подписчик события без топика."""


async def undecorated(_event: OrderCreated, _session: AsyncSession) -> None:
    """Функция, которую забыли пометить декоратором."""


def test_decorator_returns_the_function_untouched() -> None:
    assert subscribed_events(notify) == (OrderCreated,)
    assert subscribed_events(audit) == (OrderCreated, OrderShipped)


def test_undecorated_function_has_no_declaration() -> None:
    assert subscribed_events(undecorated) is None


def test_subscribe_without_events_is_pointless() -> None:
    with pytest.raises(ValueError, match="at least one event"):
        subscribe()


def test_registry_indexes_topics_and_subscribers() -> None:
    registry = build_event_registry(
        (
            Module(name="orders", subscribers=(notify,)),
            Module(name="audit", subscribers=(audit,)),
        )
    )

    assert registry.event_for("order.created") is OrderCreated
    assert registry.event_for("order.shipped") is OrderShipped
    assert registry.subscribers_for(OrderCreated) == (notify, audit)
    assert registry.subscribers_for(OrderShipped) == (audit,)


def test_unknown_topic_is_answered_with_none() -> None:
    """Решение про DLQ принимает потребитель, поэтому здесь исключения нет."""
    registry = build_event_registry((Module(name="orders", subscribers=(notify,)),))

    assert registry.event_for("legacy.thing") is None
    assert registry.subscribers_for(OrderShipped) == ()


def test_empty_registry_is_valid() -> None:
    registry = build_event_registry((Module(name="health"),))

    assert registry.event_for("order.created") is None


def test_subscriber_without_decorator_is_rejected() -> None:
    with pytest.raises(EventRegistryError, match="not decorated with @subscribe"):
        build_event_registry((Module(name="orders", subscribers=(undecorated,)),))


def test_two_classes_on_one_topic_are_rejected() -> None:
    with pytest.raises(EventRegistryError, match="claimed by two event classes"):
        build_event_registry(
            (
                Module(name="orders", subscribers=(notify,)),
                Module(name="legacy", subscribers=(handle_twin,)),
            )
        )


def test_event_without_topic_is_rejected_at_startup() -> None:
    with pytest.raises(TypeError, match="Untopiced declares no topic"):
        build_event_registry((Module(name="orders", subscribers=(handle_untopiced,)),))


def test_indexes_are_read_only() -> None:
    """Реестр собирается один раз на старте и не должен меняться в рантайме."""
    registry = build_event_registry((Module(name="orders", subscribers=(notify,)),))

    with pytest.raises(TypeError):
        registry.topics["order.created"] = OrderShipped  # type: ignore[index]
