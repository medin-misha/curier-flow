## Шаг 7. Задачи

`tasks.py` — если есть фоновая работа:

```python
"""Периодические задачи модуля notes."""

from datetime import timedelta

from app.kernel.db import session as db_session
from app.modules.notes.services import purge_old_notes
from app.platform.taskiq import schedule


@schedule(interval=timedelta(hours=1))
async def purge_notes() -> int:
    """Удалить заметки старше срока хранения."""
    return await purge_old_notes(session_factory=db_session.session_factory)
```

- `@schedule(cron=...)` или `@schedule(interval=...)`; расписание берётся из
  настроек модуля, а не зашивается числом;
- фабрика сессий читается из модуля (`db_session.session_factory`), а не
  импортируется по имени: тесты подменяют глобаль ядра;
- имя задачи в очереди — `<модуль>.<функция>`, оно живёт дольше выкатки;
- задача переживает параллельный запуск в нескольких воркерах
  (`FOR UPDATE SKIP LOCKED`) и не падает целиком из-за одного элемента: отказ
  по элементу — запись в лог и следующий элемент;
- клиентов внешних сервисов задача создаёт сама на каждый запуск: `lifespan`
  модуля поднимает только приложение FastAPI, воркер его не исполняет.

Образец с обоими видами расписания и созданием клиента —
`modules/storage/tasks.py`.
