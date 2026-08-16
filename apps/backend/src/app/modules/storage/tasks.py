"""Периодические задачи модуля storage.

Обе задачи — уборка за клиентом: одна убирает загрузки, которые никто не
подтвердил, вторая доводит до конца удаление. Обе безопасны при параллельном
запуске в нескольких воркерах и не падают целиком из-за одного файла — вся
логика в `services.py`, здесь только расписание и клиент хранилища.

Клиент создаётся на каждый запуск, а не один раз на процесс: `lifespan`
модуля поднимает только приложение FastAPI, а воркер его не исполняет.
Долгоживущий клиент здесь пришлось бы держать в глобали, которую некому
закрыть при остановке; задачи же просыпаются раз в минуту и реже, и создание
клиента на их фоне не стоит ничего.
"""

from datetime import timedelta

from app.kernel.db import session as db_session
from app.modules.storage.services import (
    FileStorage,
    delete_marked,
    storage_settings,
    sweep_orphans,
)
from app.platform.s3 import s3_settings, storage
from app.platform.taskiq import schedule


@schedule(cron=storage_settings.orphan_sweep_cron)
async def sweep_orphaned_uploads() -> int:
    """Убрать брошенные загрузки: строки `pending` старше TTL и их объекты.

    Клиент вправе исчезнуть между получением ссылки и подтверждением; без
    уборки такие строки и объекты копились бы вечно.
    """
    async with storage(s3_settings) as objects:
        return await sweep_orphans(
            session_factory=db_session.session_factory,
            storage=FileStorage(objects=objects, limits=storage_settings),
        )


@schedule(interval=timedelta(seconds=storage_settings.deletion_interval))
async def delete_marked_files() -> int:
    """Удалить объекты и строки файлов, помеченных к удалению."""
    async with storage(s3_settings) as objects:
        return await delete_marked(
            session_factory=db_session.session_factory,
            storage=FileStorage(objects=objects, limits=storage_settings),
        )
