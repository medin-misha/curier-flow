## Итог: что должно было измениться

```
src/app/modules/<name>/**      новый каталог целиком
src/app/modules/__init__.py    импорт манифеста + его имя в MODULES
alembic/versions/<...>.py      новая миграция
tests/test_<name>.py           тесты модуля
.env.example                   только если у модуля есть настройки
```

Больше ничего. `kernel/config.py`, `alembic/env.py`, `api/router.py`,
`main.py`, `worker.py`, `pyproject.toml` при добавлении модуля не трогаются —
проверь это командой `git status` перед коммитом.
