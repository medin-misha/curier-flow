"""Фоновый процесс: сборка из реестра и корректное завершение по SIGTERM.

Остановку проверяет настоящий процесс, а не вызов функции: SIGTERM приходит
операционной системе, а не приложению, и то, что событие взводится из
обработчика сигнала asyncio, внутри одного event loop не проверить.
"""

import ast
import signal
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import IO, Any
from unittest.mock import Mock

import pytest
from aio_pika.abc import AbstractChannel

import app
from app.kernel.events.outbox import DOMAIN_EVENTS_TOPOLOGY, outbox_settings
from app.kernel.events.registry import build_event_registry
from app.kernel.idempotency import idempotency_settings
from app.kernel.registry import ConsumerDecl, Module, TopologyDecl
from app.platform.idempotency import processed_messages_settings
from app.platform.taskiq import build_broker
from app.worker import (
    SYSTEM_MODULE,
    build_system_module,
    collect_consumers,
    collect_topology,
    worker_settings,
)

WORKER_SOURCE = Path(app.__file__).resolve().parent / "worker.py"

#: Сколько ждать строки в выводе процесса, прежде чем считать его зависшим.
STARTUP_TIMEOUT = 60.0
SHUTDOWN_TIMEOUT = 30.0

#: Заведомо нерабочие адреса: сборка брокера в сеть ходить не должна.
BROKER_ARGS: dict[str, Any] = {
    "amqp_dsn": "amqp://guest:guest@127.0.0.1:1/",
    "redis_dsn": "redis://127.0.0.1:1/0",
    "result_ttl": 60,
}


def system_module() -> Module:
    """Системный манифест с каналом-заглушкой: он только лежит в замыканиях."""
    return build_system_module(Mock(spec=AbstractChannel), build_event_registry([]))


async def handle(_message: object, _session: object) -> None: ...


def test_topology_is_collected_in_registry_order() -> None:
    first = TopologyDecl(exchange="a", queue="a.q", routing_key="#")
    second = TopologyDecl(exchange="b", queue="b.q", routing_key="#")
    modules = (
        Module(name="orders", topology=(first,)),
        Module(name="health"),
        Module(name="billing", topology=(second,)),
    )

    assert collect_topology(modules) == (first, second)


def test_consumers_are_collected_in_registry_order() -> None:
    first = ConsumerDecl(queue="a.q", handler=handle)
    second = ConsumerDecl(queue="b.q", handler=handle)
    modules = (
        Module(name="orders", consumers=(first, second)),
        Module(name="health"),
    )

    assert collect_consumers(modules) == (first, second)


def test_empty_registry_yields_nothing_to_run() -> None:
    assert collect_topology(()) == ()
    assert collect_consumers(()) == ()


def test_defaults_match_the_env_example() -> None:
    assert worker_settings.shutdown_timeout == 30.0
    assert worker_settings.max_concurrent_tasks == 10


def test_system_module_carries_the_outbox_machinery() -> None:
    """Релей, уборка и доставка подписчикам подключаются тем же реестром."""
    module = system_module()

    assert module.name == SYSTEM_MODULE
    assert module.router is None
    assert module.topology == (DOMAIN_EVENTS_TOPOLOGY,)
    assert [decl.queue for decl in module.consumers] == [DOMAIN_EVENTS_TOPOLOGY.queue]
    # Доставка at-least-once: отметка об обработке обязательна.
    assert module.consumers[0].requires_idempotency


def test_system_tasks_are_scheduled_from_the_settings() -> None:
    broker = build_broker([system_module()], **BROKER_ARGS)

    relay = broker.find_task("system.relay_outbox_events")
    purge = broker.find_task("system.purge_outbox_events")

    assert relay is not None
    assert purge is not None
    assert relay.labels["schedule"] == [
        {"interval": timedelta(seconds=outbox_settings.relay_interval)}
    ]
    assert purge.labels["schedule"] == [{"cron": outbox_settings.cleanup_cron}]


def test_service_tables_have_a_cleanup_task() -> None:
    """Служебные таблицы растут на каждой операции сервиса и не убывают сами."""
    broker = build_broker([system_module()], **BROKER_ARGS)

    keys = broker.find_task("system.purge_idempotency_keys")
    marks = broker.find_task("system.purge_message_marks")

    assert keys is not None
    assert marks is not None
    assert keys.labels["schedule"] == [{"cron": idempotency_settings.cleanup_cron}]
    assert marks.labels["schedule"] == [{"cron": processed_messages_settings.cleanup_cron}]


def test_system_module_joins_the_registry_last() -> None:
    """Порядок объявления сохраняется: сперва бизнес-модули, потом системный."""
    module = Module(
        name="orders", topology=(TopologyDecl(exchange="a", queue="a.q", routing_key="#"),)
    )
    modules = (module, system_module())

    assert collect_topology(modules)[-1] == DOMAIN_EVENTS_TOPOLOGY
    assert collect_consumers(modules)[-1].queue == DOMAIN_EVENTS_TOPOLOGY.queue


def test_worker_is_runnable_as_a_module() -> None:
    """`python -m app.worker` — точка входа образа и цели `make worker`."""
    tree = ast.parse(WORKER_SOURCE.read_text(encoding="utf-8"), filename=str(WORKER_SOURCE))
    guards = [
        node
        for node in tree.body
        if isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
    ]

    assert guards, "worker.py must call main() under an `if __name__ == '__main__'` guard"


def read_until(stream: IO[str], needle: str, timeout: float) -> list[str]:
    """Читать вывод процесса до нужной строки; иначе — понятная ошибка."""
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        line = stream.readline()
        if not line:
            break
        seen.append(line)
        if needle in line:
            return seen
    raise AssertionError(f"worker never printed {needle!r}; output:\n{''.join(seen)}")


def test_worker_starts_and_stops_on_sigterm(
    rabbitmq_dsn: str,
    redis_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RABBITMQ_DSN", rabbitmq_dsn)
    monkeypatch.setenv("REDIS_DSN", redis_dsn)
    monkeypatch.setenv("WORKER_SHUTDOWN_TIMEOUT", "5")
    monkeypatch.setenv("LOG_FORMAT", "json")
    # Пустой каталог: воркер не должен подхватить .env разработчика.
    monkeypatch.chdir(tmp_path)

    process = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    # Сторож на случай, если процесс не напечатает вообще ничего: без него
    # readline() повесил бы прогон целиком.
    watchdog = threading.Timer(STARTUP_TIMEOUT + SHUTDOWN_TIMEOUT, process.kill)
    watchdog.start()
    try:
        assert process.stdout is not None
        read_until(process.stdout, "worker.started", STARTUP_TIMEOUT)

        process.send_signal(signal.SIGTERM)
        tail = process.communicate(timeout=SHUTDOWN_TIMEOUT)[0]
    finally:
        watchdog.cancel()
        process.kill()

    assert process.returncode == 0, tail
    assert "worker.stopped" in tail
