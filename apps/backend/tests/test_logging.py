"""Логирование: единый конвейер и контекст запроса в каждой записи."""

import json
import logging
from collections.abc import Iterator
from uuid import UUID

import pytest
import structlog

from app.kernel.context import actor_id, request_id
from app.kernel.logging import add_request_context
from tests.logs import capture_logs

ACTOR = UUID("018f5b4c-0000-7000-8000-0000000000ff")


@pytest.fixture
def request_context() -> Iterator[None]:
    """Контекст запроса, гарантированно снятый после теста."""
    request_token = request_id.set("trace-123")
    actor_token = actor_id.set(ACTOR)
    yield
    request_id.reset(request_token)
    actor_id.reset(actor_token)


def test_processor_adds_request_context(request_context: None) -> None:  # noqa: ARG001
    event = add_request_context(None, "info", {"event": "widget.created"})

    assert event["request_id"] == "trace-123"
    assert event["actor_id"] == str(ACTOR)


def test_processor_keeps_actor_out_when_unknown() -> None:
    """Вне запроса actor_id неизвестен, и ключа со значением null быть не должно."""
    event = add_request_context(None, "info", {"event": "outbox.relayed"})

    assert event["request_id"] == "-"
    assert "actor_id" not in event


def test_structlog_records_are_rendered_as_json(request_context: None) -> None:  # noqa: ARG001
    with capture_logs() as stream:
        structlog.get_logger("app.tests").info("widget.created", widget_id=7)

    record = json.loads(stream.getvalue())
    assert record["event"] == "widget.created"
    assert record["widget_id"] == 7
    assert record["level"] == "info"
    assert record["logger"] == "app.tests"
    assert record["request_id"] == "trace-123"
    assert record["actor_id"] == str(ACTOR)
    assert record["timestamp"].endswith("Z")


def test_stdlib_records_go_through_the_same_pipeline(request_context: None) -> None:  # noqa: ARG001
    """Логи uvicorn и SQLAlchemy не должны выпадать из общего формата."""
    with capture_logs() as stream:
        logging.getLogger("uvicorn.error").warning("Server is shutting down")

    record = json.loads(stream.getvalue())
    assert record["event"] == "Server is shutting down"
    assert record["logger"] == "uvicorn.error"
    assert record["level"] == "warning"
    assert record["request_id"] == "trace-123"


def test_console_format_is_human_readable() -> None:
    with capture_logs(log_format="console") as stream:
        structlog.get_logger("app.tests").info("widget.created", widget_id=7)

    output = stream.getvalue()
    assert "widget.created" in output
    assert "widget_id=7" in output
    assert not output.lstrip().startswith("{")


def test_traceback_is_rendered_into_json() -> None:
    with capture_logs() as stream:
        try:
            raise RuntimeError("kaboom")
        except RuntimeError:
            structlog.get_logger("app.tests").exception("task.failed")

    record = json.loads(stream.getvalue())
    assert record["event"] == "task.failed"
    assert "RuntimeError: kaboom" in record["exception"]


def test_reconfiguration_does_not_duplicate_output() -> None:
    with capture_logs() as stream:
        with capture_logs() as inner:
            structlog.get_logger("app.tests").info("once")
        assert len(inner.getvalue().splitlines()) == 1

    assert stream.getvalue() == ""
