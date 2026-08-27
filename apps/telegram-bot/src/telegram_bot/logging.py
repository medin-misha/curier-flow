"""Структурное логирование с безопасными процессорами."""

import logging
import sys
from typing import Any

import structlog


def configure_logging(*, level: str, format_name: str) -> None:
    """Настроить structlog и заглушить HTTP-логи с token-bearing URL."""
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
        force=True,
    )
    # Telegram token является частью URL Bot API. INFO-лог httpx показал бы его.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # AMQP debug records могут включать repr Message вместе с исходным body.
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)

    renderer: Any
    if format_name == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
