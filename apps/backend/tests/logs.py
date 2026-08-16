"""Перехват вывода логов для тестов.

Логи проверяются через настоящий конвейер `configure_logging`, а не через
`structlog.testing.capture_logs`: последний подменяет цепочку процессоров
целиком, и именно тот процессор, который подмешивает `request_id`, до записи
не доходит — тест зеленел бы при сломанном логировании.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO

from app.kernel.config import LogFormat
from app.kernel.logging import configure_logging


@contextmanager
def capture_logs(*, log_format: LogFormat = "json") -> Iterator[StringIO]:
    """Направить логи процесса в буфер и вернуть настройки обратно на выходе."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level

    stream = StringIO()
    configure_logging(level="DEBUG", log_format=log_format)
    for handler in root.handlers:
        assert isinstance(handler, logging.StreamHandler)
        handler.setStream(stream)

    try:
        yield stream
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
