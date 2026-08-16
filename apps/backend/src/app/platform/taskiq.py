"""Брокер задач TaskIQ: сборка брокера, шедулера и регистрация задач модулей.

TaskIQ отвечает за нашу собственную работу — отложенные и периодические
задачи, повторы, релей outbox. Обмен сообщениями с чужими сервисами идёт через
`app.platform.rabbitmq`: у них разный жизненный цикл (задачу мы вправе
переписать и перезапустить, чужое сообщение — нет) и разные требования к
очередям, а общая очередь лишила бы возможности масштабировать их отдельно.

Транспорт задач — тот же RabbitMQ, а хранилище результатов — Redis. У брокера
результатов работы нет: очередь доставляет сообщение и забывает о нём, поэтому
`kiq()` без внешнего хранилища не смог бы вернуть результат вызывающему.
Из того, что умеет TaskIQ, Redis — единственный вариант, который переживает
перезапуск процесса, виден всем процессам сразу (задачу ставит API, выполняет
воркер, результат читает снова API) и сам удаляет протухшие записи по TTL.
In-memory backend этого не даёт, а класть результаты в Postgres значило бы
нагружать транзакционную базу данными со сроком жизни в сутки.

Задачи не регистрируются декоратором на импорте. Модуль перечисляет корутины в
своём манифесте, а связывает их с брокером сборка процесса — иначе состав
очереди зависел бы от того, чей `tasks.py` кто-то успел импортировать.
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Any, Final

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from taskiq import AsyncBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisAsyncResultBackend

from app.kernel.registry import Module

#: Атрибут, в котором `schedule` хранит расписание до регистрации в брокере.
#: Имя объявлено один раз: его читает `_register_tasks`, и разъехаться они
#: не должны.
SCHEDULE_ATTR: Final = "__taskiq_schedule__"

#: Задача модуля: корутина, которую платформа зарегистрирует в брокере.
Task = Callable[..., Awaitable[Any]]

#: Суффикс, который TaskIQ дописывает к `__name__` исходной функции при
#: регистрации, чтобы декорированная задача заняла её имя в модуле. Имя задачи
#: обязано быть одинаковым при каждой сборке брокера, поэтому суффикс
#: отбрасывается: иначе вторая сборка в том же процессе дала бы другое имя.
_RENAMED_SUFFIX: Final = "__taskiq_original"


class RedisSettings(BaseSettings):
    """Настройки хранилища результатов задач."""

    model_config = SettingsConfigDict(
        env_prefix="redis_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dsn: RedisDsn = RedisDsn("redis://localhost:6379/0")

    #: Сколько секунд хранится результат задачи. Без ограничения Redis копил бы
    #: их вечно: результат нужен тому, кто поставил задачу, и только пока он
    #: его ждёт.
    result_ttl: int = Field(default=86400, ge=1)


#: Единственный экземпляр настроек процесса. Соединений на импорте не создаётся.
redis_settings = RedisSettings()


def schedule(
    *,
    cron: str | None = None,
    interval: timedelta | None = None,
    cron_offset: str | timedelta | None = None,
) -> Callable[[Task], Task]:
    """Пометить задачу расписанием для `TaskiqScheduler`.

    Принимает cron-выражение и/или интервал, возвращает декоратор, который
    возвращает исходную функцию нетронутой. Кидает `ValueError`, если не задано
    ни одного условия запуска.

    Декоратор помечает, а не регистрирует: брокер создаётся в момент запуска
    процесса из настроек, и `@broker.task` требовал бы глобального брокера на
    импорте. Расписание читает `build_broker` — из тех же манифестов, из
    которых собирается всё остальное.
    """
    if cron is None and interval is None:
        raise ValueError("schedule() needs either cron or interval")

    entry: dict[str, Any] = {}
    if cron is not None:
        entry["cron"] = cron
    if cron_offset is not None:
        entry["cron_offset"] = cron_offset
    if interval is not None:
        entry["interval"] = interval

    def decorate(task: Task) -> Task:
        setattr(task, SCHEDULE_ATTR, [entry])
        return task

    return decorate


def task_name(module: Module, task: Task) -> str:
    """Имя задачи в очереди: `<модуль>.<функция>`.

    Имя уезжает в сообщение и живёт в очереди дольше выкатки, поэтому оно
    выводится в одном месте: воркер ищет задачу по имени из сообщения, и
    расхождение с тем, что положил отправитель, выглядит как «задача пропала».
    Полный путь модуля Python не годится — переезд файла переименовал бы
    задачу и осиротил всё, что уже стоит в очереди.
    """
    original, _, _ = task.__name__.partition(_RENAMED_SUFFIX)
    return f"{module.name}.{original}"


def build_broker(
    modules: Sequence[Module],
    *,
    amqp_dsn: str,
    redis_dsn: str,
    result_ttl: int,
) -> AsyncBroker:
    """Собрать брокер задач и зарегистрировать в нём задачи модулей.

    Принимает реестр модулей и адреса инфраструктуры, возвращает готовый, но
    ещё не подключённый брокер: соединение открывает `startup()`, который
    зовёт воркер. Кидает `ValueError`, если два модуля дали задачам одно имя.

    Отдельная фабрика, а не глобальный объект: тесты собирают брокер со своим
    набором модулей, а процесс uvicorn не должен получать его как побочный
    эффект импорта.
    """
    # Хранилище результатов подключается методом, а не аргументом конструктора:
    # передача через конструктор в taskiq 0.12 объявлена устаревшей.
    broker: AsyncBroker = AioPikaBroker(url=amqp_dsn).with_result_backend(
        RedisAsyncResultBackend[Any](redis_url=redis_dsn, result_ex_time=result_ttl)
    )
    _register_tasks(broker, modules)
    return broker


def build_scheduler(broker: AsyncBroker) -> TaskiqScheduler:
    """Собрать шедулер поверх уже настроенного брокера.

    Принимает брокер с зарегистрированными задачами, возвращает шедулер.

    Источник расписаний один — метки самих задач: расписание периодической
    задачи это её свойство, и держать его отдельно от кода задачи значит
    получить две правды. Источник в Redis (расписания, создаваемые в рантайме)
    добавляется тогда, когда появится сценарий «пользователь назначает время»,
    а не заранее.
    """
    return TaskiqScheduler(broker, [LabelScheduleSource(broker)])


def _register_tasks(broker: AsyncBroker, modules: Sequence[Module]) -> None:
    """Зарегистрировать задачи всех модулей, не допуская совпадения имён.

    Совпавшие имена — не мелочь: TaskIQ хранит задачи в словаре, и вторая
    молча вытеснила бы первую, а сообщения первой начали бы выполнять чужой
    код. Такое ловится на старте процесса.
    """
    for module in modules:
        for task in module.tasks:
            name = task_name(module, task)
            if broker.find_task(name) is not None:
                raise ValueError(
                    f"Task name '{name}' is already registered: two tasks in module "
                    f"'{module.name}' cannot share a function name."
                )
            labels: dict[str, Any] = {}
            declared = getattr(task, SCHEDULE_ATTR, None)
            if declared is not None:
                labels["schedule"] = declared
            broker.register_task(task, task_name=name, **labels)
