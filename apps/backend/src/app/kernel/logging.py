"""Настройка логирования: один конвейер на весь процесс.

Логи разбирает машина, а не только человек, поэтому формат обязан быть один
для всего процесса — и для наших вызовов structlog, и для чужих записей через
стандартный `logging` (uvicorn, SQLAlchemy, alembic, aio-pika). Чужие записи
пропускаются через `ProcessorFormatter`: без него половина строк в проде
оказалась бы plain text посреди JSON и потерялась бы при разборе.

`request_id` и `actor_id` подмешивает процессор, а не автор каждого вызова:
пропущенный вручную идентификатор обнаруживается ровно в тот момент, когда по
нему нужно связать записи упавшего запроса.
"""

import logging
import sys
from typing import Final

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.kernel.config import LogFormat, LogLevel, settings
from app.kernel.context import actor_id, request_id

#: Логгеры, которым сторонние библиотеки ставят собственные обработчики.
#: Uvicorn делает это до импорта приложения, и без сброса каждая его строка
#: печаталась бы дважды: своим форматом и нашим.
_FOREIGN_LOGGERS: Final = ("uvicorn", "uvicorn.error", "uvicorn.access")


def add_request_context(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Подмешать в запись идентификатор запроса и действующее лицо.

    Принимает и возвращает запись structlog. `actor_id` добавляется только
    когда он известен: ключ со значением null в каждой строке лога ничего не
    сообщает, но занимает место в индексе хранилища.
    """
    event_dict["request_id"] = request_id.get()
    actor = actor_id.get()
    if actor is not None:
        event_dict["actor_id"] = str(actor)
    return event_dict


def configure_logging(
    *,
    level: LogLevel | None = None,
    log_format: LogFormat | None = None,
) -> None:
    """Настроить structlog и стандартный logging на общий конвейер.

    Вызывается один раз в точке входа процесса (`main.py`, `worker.py`) до
    первой записи. Аргументы перекрывают настройки процесса — это нужно
    воркеру и тестам, которым важен предсказуемый формат вывода.

    Повторный вызов безопасен: обработчики корневого логгера заменяются, а не
    добавляются, иначе каждая перенастройка удваивала бы вывод.
    """
    resolved_level = level or settings.log_level
    resolved_format = log_format or settings.log_format

    #: Общая часть конвейера. Одна и та же и для structlog, и для чужих
    #: записей: иначе в логах соседних строк разъезжается набор полей.
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        # Рендерит не structlog, а обработчик стандартного logging: только так
        # наши записи и чужие проходят один и тот же финальный форматтер.
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=_renderers(resolved_format),
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved_level)

    for name in _FOREIGN_LOGGERS:
        foreign = logging.getLogger(name)
        foreign.handlers.clear()
        foreign.propagate = True


def _renderers(log_format: LogFormat) -> list[Processor]:
    """Хвост конвейера: как запись превращается в строку."""
    if log_format == "json":
        return [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # JSONRenderer не умеет сериализовать кортеж exc_info, поэтому
            # трейсбек разворачивается в строку заранее.
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    return [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        # ConsoleRenderer печатает трейсбек сам и с подсветкой, поэтому
        # format_exc_info в этой ветке только испортил бы вывод.
        structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
    ]
