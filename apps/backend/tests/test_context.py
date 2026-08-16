"""Контекст операции: значения по умолчанию и изоляция между задачами."""

import asyncio
from uuid import uuid4

from app.kernel.context import actor_id, request_id


def test_defaults_are_safe_outside_request() -> None:
    """Логи и миграции обращаются к контексту вне запроса — там не должно падать."""
    assert request_id.get() == "-"
    assert actor_id.get() is None


async def test_child_task_does_not_leak_into_parent() -> None:
    """Контекст копируется в дочернюю задачу, но не возвращается из неё."""

    async def child() -> str:
        request_id.set("child")
        return request_id.get()

    token = request_id.set("parent")
    try:
        assert await asyncio.create_task(child()) == "child"
        assert request_id.get() == "parent"
    finally:
        request_id.reset(token)


def test_actor_holds_uuid() -> None:
    actor = uuid4()
    token = actor_id.set(actor)
    try:
        assert actor_id.get() == actor
    finally:
        actor_id.reset(token)
    assert actor_id.get() is None
