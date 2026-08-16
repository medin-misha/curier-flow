---
paths:
  - "src/app/**/*.py"
  - "alembic/env.py"
  - "tests/**/*.py"
---

# Правила зависимостей

`api → modules → platform → kernel`. Стрелка означает «вправе импортировать».

- `kernel` не импортирует ни `platform`, ни `modules`, ни `api`;
- `kernel` не импортирует `fastapi` и `starlette` в рантайме. Единственное
  исключение — `registry.py`, где типы фреймворка нужны в аннотациях: там они
  живут под `if TYPE_CHECKING:` и зависимости не создают;
- `platform` не импортирует `modules` и `api`;
- бизнес-модули **не импортируют друг друга** — только через доменные события;
- модуль не импортирует `app.api.deps`: нужные псевдонимы (`Uow`, `RoSession`,
  `PageQuery`) он объявляет у себя из тех же функций ядра;
- `main.py` и `app/api/**` не импортируют `app.platform` — ни в рантайме, ни в
  аннотациях: фоновой работы в процессе uvicorn нет;
- `alembic/env.py` зависит от `kernel` и `modules`, но не от `api`.

**Проверяют:** `uv run lint-imports` (контракты `Layers` и
`Business modules never import each other`),
`tests/test_kernel_isolation.py`, `tests/test_process_isolation.py`,
`tests/test_project_layout.py`.
