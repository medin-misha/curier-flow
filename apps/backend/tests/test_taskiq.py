"""Сборка брокера задач: регистрация из реестра, имена, расписания.

Соединения здесь не открываются намеренно: `build_broker` обязан быть чистой
сборкой объекта, а подключение — отдельным шагом, который делает воркер.
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from taskiq import AsyncBroker
from taskiq.schedule_sources import LabelScheduleSource

from app.kernel.registry import Module
from app.platform.taskiq import build_broker, build_scheduler, redis_settings, schedule, task_name

BROKER_ARGS: dict[str, Any] = {
    # Заведомо нерабочие адреса: если сборка куда-то полезет, тест упадёт.
    "amqp_dsn": "amqp://guest:guest@127.0.0.1:1/",
    "redis_dsn": "redis://127.0.0.1:1/0",
    "result_ttl": 60,
}


async def send_report() -> str:
    return "sent"


async def rebuild_index() -> None: ...


def module_with(*tasks: Callable[..., Any], name: str = "reports") -> Module:
    return Module(name=name, tasks=tasks)


def test_task_name_is_module_scoped() -> None:
    assert task_name(module_with(), send_report) == "reports.send_report"


def test_task_name_survives_a_second_registration() -> None:
    """TaskIQ переименовывает исходную функцию, а имя задачи меняться не должно."""

    async def rebuild() -> None: ...

    module = module_with(rebuild, name="search")
    first = build_broker([module], **BROKER_ARGS)
    second = build_broker([module], **BROKER_ARGS)

    assert list(first.get_all_tasks()) == list(second.get_all_tasks()) == ["search.rebuild"]


def test_tasks_are_registered_from_the_registry() -> None:
    broker = build_broker([module_with(send_report, rebuild_index)], **BROKER_ARGS)

    assert set(broker.get_all_tasks()) == {"reports.send_report", "reports.rebuild_index"}


def test_same_function_name_in_one_module_is_rejected() -> None:
    async def send_report() -> None: ...

    with pytest.raises(ValueError, match=r"reports\.send_report"):
        build_broker(
            [module_with(globals()["send_report"], send_report)],
            **BROKER_ARGS,
        )


def test_modules_without_tasks_are_fine() -> None:
    broker = build_broker([Module(name="health")], **BROKER_ARGS)

    assert broker.get_all_tasks() == {}


def test_registered_task_keeps_working_as_a_function() -> None:
    build_broker([module_with(send_report)], **BROKER_ARGS)

    assert asyncio.run(send_report()) == "sent"


def test_schedule_marks_the_task_without_registering_it() -> None:
    @schedule(cron="*/5 * * * *")
    async def sweep() -> None: ...

    broker = build_broker([module_with(sweep, name="storage")], **BROKER_ARGS)
    task = broker.find_task("storage.sweep")

    assert task is not None
    assert task.labels["schedule"] == [{"cron": "*/5 * * * *"}]


def test_schedule_accepts_an_interval() -> None:
    @schedule(interval=timedelta(seconds=30))
    async def relay() -> None: ...

    broker = build_broker([module_with(relay, name="outbox")], **BROKER_ARGS)
    task = broker.find_task("outbox.relay")

    assert task is not None
    assert task.labels["schedule"] == [{"interval": timedelta(seconds=30)}]


def test_schedule_carries_a_cron_offset() -> None:
    """Расписание в местном времени: cron без смещения считается в UTC."""

    @schedule(cron="0 9 * * *", cron_offset="Europe/Moscow")
    async def digest() -> None: ...

    broker = build_broker([module_with(digest, name="reports")], **BROKER_ARGS)
    task = broker.find_task("reports.digest")

    assert task is not None
    assert task.labels["schedule"] == [{"cron": "0 9 * * *", "cron_offset": "Europe/Moscow"}]


def test_schedule_without_a_trigger_is_rejected() -> None:
    with pytest.raises(ValueError, match="cron or interval"):
        schedule()


async def test_scheduler_reads_schedules_from_task_labels() -> None:
    @schedule(cron="0 3 * * *")
    async def nightly() -> None: ...

    broker = build_broker([module_with(nightly, name="storage")], **BROKER_ARGS)
    scheduler = build_scheduler(broker)
    source = scheduler.sources[0]
    await source.startup()
    scheduled = await source.get_schedules()

    assert isinstance(source, LabelScheduleSource)
    assert [(task.task_name, task.cron) for task in scheduled] == [("storage.nightly", "0 3 * * *")]


def test_unscheduled_tasks_produce_no_schedule() -> None:
    broker = build_broker([module_with(send_report)], **BROKER_ARGS)
    task = broker.find_task("reports.send_report")

    assert task is not None
    assert "schedule" not in task.labels


def test_build_broker_opens_no_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Брокер собирается в процессе, который в сеть ходить не должен."""

    async def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("build_broker must not connect")

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "create_connection", refuse)
    broker = build_broker([module_with(send_report)], **BROKER_ARGS)

    assert isinstance(broker, AsyncBroker)


def test_result_ttl_defaults_to_a_day() -> None:
    assert redis_settings.result_ttl == 86400
