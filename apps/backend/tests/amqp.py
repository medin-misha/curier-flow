"""Обвязка тестов, которые ходят в настоящий брокер.

Ожидание вместо фиксированной паузы: доставка асинхронна, и `sleep` либо
удлиняет каждый прогон, либо мигает на загруженной машине. Здесь же
уникальные имена: брокер в контейнере один на весь прогон, и очередь,
названная по имени теста, доживёт до следующего.
"""

import asyncio
from uuid import uuid4

from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from app.platform.rabbitmq import open_channel


def unique(prefix: str) -> str:
    """Уникальное имя: брокер в контейнере один на весь прогон."""
    return f"{prefix}.{uuid4().hex[:8]}"


async def wait_for_message(
    conn: AbstractRobustConnection,
    queue_name: str,
    wait_for: float = 15.0,
) -> AbstractIncomingMessage:
    """Дождаться сообщения в очереди и забрать его."""
    deadline = asyncio.get_running_loop().time() + wait_for
    async with open_channel(conn) as channel:
        queue = await channel.get_queue(queue_name)
        while asyncio.get_running_loop().time() < deadline:
            message = await queue.get(no_ack=True, fail=False)
            if message is not None:
                return message
            await asyncio.sleep(0.05)
    raise AssertionError(f"no message arrived in {queue_name}")


async def message_count(conn: AbstractRobustConnection, queue_name: str) -> int:
    """Сколько сообщений ждёт в очереди прямо сейчас.

    Канал открывается заново на каждый вызов: RobustChannel кеширует очереди,
    объявленные passive, и второй такой вызов на том же канале вернул бы
    прошлый ответ брокера вместо нового.
    """
    async with open_channel(conn) as channel:
        queue = await channel.declare_queue(queue_name, passive=True)
        return queue.declaration_result.message_count or 0


async def wait_until_delivered(
    conn: AbstractRobustConnection,
    queue_name: str,
    wait_for: float = 15.0,
) -> None:
    """Дождаться, пока в очереди не останется неразобранных сообщений."""
    deadline = asyncio.get_running_loop().time() + wait_for
    while asyncio.get_running_loop().time() < deadline:
        if await message_count(conn, queue_name) == 0:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"queue {queue_name} still holds undelivered messages")
