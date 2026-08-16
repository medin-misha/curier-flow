# Шаблон backend-сервиса: правила проекта

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL. Инфраструктура уже написана:
пользователь шаблона добавляет только бизнес-модули.

Здесь — инварианты, которые нельзя нарушать, по одному утверждению на каждый.
Обоснования, таблицы и «почему именно так» лежат в `.claude/rules/`: каждое
правило подтягивается само, когда открываешь файл, к которому оно относится.
Порядок действий для многошаговых задач — в `.claude/skills/`.

Комментарии, докстринги и документация — по-русски. Имена, сообщения об
ошибках, ключи логов и топики событий — по-английски.

## Карта проекта

```
pyproject.toml           инструменты и их конфигурация: ruff, mypy, import-linter, pytest
Makefile                 единственный интерфейс запуска: install, check, test, up, migrate, run, worker
docker-compose.yml       postgres, rabbitmq, redis, minio + процессы api и worker
.env.example             все переменные окружения с объяснением каждой
alembic/env.py           метаданные для миграций: импортирует модели по MODULES
src/app/
  main.py                точка входа uvicorn: create_app из реестра
  worker.py              точка входа фонового процесса: TaskIQ + консьюмеры + релей outbox
  api/
    router.py            сборка главного роутера из манифестов
    errors.py            исключение → RFC 9457 problem+json
    middleware.py        request_id, структурный лог запроса
    deps.py              Uow, RoSession, PageQuery, Actor, CurrentActor
    idempotency.py       обвязка Idempotency-Key поверх помеченных ручек
  kernel/
    config.py            общие настройки процесса
    context.py           contextvars: request_id, actor_id
    errors.py            AppError и наследники — без единой ссылки на HTTP
    logging.py           настройка structlog
    schemas.py           BaseRequest (extra=forbid) и BaseResponse (from_attributes)
    pagination.py        keyset-пагинация: PageParams, Page, кодек курсора
    registry.py          Module, TopologyDecl, ConsumerDecl, build_lifespan
    idempotency.py       таблица idempotency_keys и метка @idempotent
    db/                  base, mixins, session (engine, get_uow, get_ro_session), crud
    events/              bus (emit, subscribe, after_commit), models, outbox (релей), registry
    security/            passwords (argon2), tokens (JWT)
  platform/
    rabbitmq.py          соединение, топология, публикация, ConsumerGroup
    taskiq.py            брокер задач, шедулер, метка @schedule
    s3.py                клиент объектного хранилища и presigned-ссылки
    idempotency.py       run_once по processed_messages
    domain_events.py     строка outbox ↔ сообщение брокера ↔ подписчики
  modules/
    __init__.py          MODULES: список манифестов
    health/  storage/    готовые модули, они же образцы
tests/                   pytest + testcontainers (настоящие Postgres, RabbitMQ, Redis, MinIO)
docs/adr/                краткие записи о спорных решениях
.claude/rules/           правила по путям: подгружаются, когда правишь подходящий файл
.claude/skills/          порядок действий: new-module, background-effect, db-migration, pre-commit
```

## Команды

| Команда | Что делает |
| --- | --- |
| `make install` | зависимости всех групп и git-хуки |
| `make check` | `ruff format --check`, `ruff check`, `mypy`, `lint-imports` |
| `make test` | pytest с покрытием, отдельный порог на `app.kernel` (85%) |
| `make up` / `make down` | поднять/остановить стек docker compose |
| `make migrate` | `alembic upgrade head` |
| `make revision m="..."` | сгенерировать миграцию по моделям |
| `make run` | uvicorn с автоперезагрузкой |
| `make worker` | фоновый процесс: TaskIQ, консьюмеры, релей outbox |

`make check` и `make test` обязаны быть зелёными перед каждым коммитом. Тестам
нужен Docker: они поднимают настоящие Postgres, RabbitMQ, Redis и MinIO через
testcontainers, потому что шаблон опирается на `JSONB`, `SKIP LOCKED`,
`ON CONFLICT` и подпись SigV4.

## Слои и реестр модулей

`api → modules → platform → kernel`; стрелка означает «вправе импортировать».
Бизнес-модули **не импортируют друг друга** — только через доменные события.
`kernel` не знает про fastapi, процесс uvicorn не знает про `platform`.

Состав сервиса задаёт `MODULES` в `src/app/modules/__init__.py` — одна строка на
модуль и больше нигде. Автодискавери по файловой системе нет намеренно.
Подробности: `rules/layers.md`, `rules/module-layout.md`.

## Транзакции

Одна транзакция на запрос, коммит делает зависимость, а не бизнес-код. Пишущая
ручка берёт `Uow`, читающая — `RoSession`. Свой псевдоним пишущей транзакции
модуль объявляет как `Depends(get_uow, scope="function")`: без области клиент
получит 2xx на незакоммиченные данные. `session.commit()` в модуле запрещён.
Внутри открытой транзакции нет внешнего I/O — ни S3, ни HTTP, ни публикации в
брокер, ни `kiq()`. Подробности и единственное исключение: `rules/transactions.md`.

## События

Побочный эффект привязан к успешному коммиту, а не к HTTP-статусу. Эффект
нельзя потерять — `emit(session, Event(...))` в outbox; потерю переживём —
`after_commit(session, fn)`. Событие — это факт, а не команда, и контракт между
модулями — топик, а не класс. Подписчик обязан быть идемпотентным. Выбор
механизма — скилл `background-effect`, инварианты — `rules/events.md`.

## Ошибки

Наружу уходит только `application/problem+json` (RFC 9457) — от доменной ошибки,
от валидации, от 404 и от необработанного исключения одинаково. Бизнес-код
поднимает наследника `AppError` из `app.kernel.errors`; `HTTPException` запрещён
линтером во всём проекте. Подробности: `rules/errors.md`.

## Идемпотентность

Доставка везде at-least-once, «ровно один раз» на сети не существует. Защита от
повтора — запись в **ту же транзакцию**, что и сам эффект: `idempotency_keys`
для HTTP, `processed_messages` для сообщений брокера. Записывающая ручка
помечается `@idempotent` из `app.kernel.idempotency` — осознанно и только
записывающая. Неуспешный ответ ключ не занимает. Подробности:
`rules/idempotency.md`.

## Пагинация

Только keyset по `(created_at DESC, id DESC)`, `OFFSET` не используется нигде.
У пагинируемой таблицы обязан быть составной индекс, объявленный после класса
модели. Подробности: `rules/pagination.md`.

## Настройки

Окружение читается только через pydantic-settings; `os.getenv` и `os.environ`
запрещены линтером. Каждая новая переменная попадает в `.env.example` с
объяснением, и дефолт в коде совпадает с ним. Подробности: `rules/settings.md`.

## Фоновая работа

TaskIQ — наша собственная работа, RabbitMQ напрямую — обмен с чужими сервисами.
И то и другое живёт **только** в процессе `worker.py`: фоновая работа в uvicorn
умирает при перекатке и размножается вместе с числом веб-воркеров. Подробности:
`rules/background-work.md`.

## Стиль

Действует пользовательское правило `code-style`. Сверх него: в `kernel` и
`platform` докстринги обязательны и `mypy` строже — `rules/kernel-and-platform.md`.
Схема меняется только миграцией — скилл `db-migration`, `rules/migrations.md`.

## Перед коммитом

Скилл `pre-commit`: `make check`, `make test`, миграции, плюс то, чего линтер не
ловит — выбор `emit()`/`after_commit`, нужность `@idempotent`, keyset-индекс,
полнота `.env.example`. Соответствие «правило → проверка» в обе стороны —
`.claude/skills/pre-commit/references/rule-to-check.md`.

## Где что искать

| Файл `.claude/rules/` | Грузится, когда правишь |
| --- | --- |
| `layers.md` | любой `src/app/**`, `alembic/env.py`, `tests/**` |
| `module-layout.md` | `src/app/modules/**` |
| `transactions.md` | модули, `api/**`, `kernel/db/**` |
| `events.md` | модули, `kernel/events/**`, `platform/domain_events.py` |
| `background-work.md` | `tasks.py`, `consumers.py`, `worker.py`, `platform/taskiq.py`, `platform/rabbitmq.py` |
| `errors.md` | модули, `api/**`, `kernel/errors.py` |
| `pagination.md` | модули, `kernel/pagination.py`, `kernel/db/crud.py` |
| `settings.md` | любой `config.py`, модули, `platform/**`, `.env.example` |
| `migrations.md` | `alembic/**`, любой `models/**` |
| `idempotency.md` | три файла `idempotency.py` и `handlers.py` модулей |
| `kernel-and-platform.md` | `kernel/**`, `platform/**` |

| Скилл | Когда |
| --- | --- |
| `new-module` | новый бизнес-модуль целиком |
| `background-effect` | «после X должно случиться Y», фоновая или периодическая работа, чужая очередь |
| `db-migration` | изменение схемы базы |
| `pre-commit` | перед коммитом |

У каждого модуля есть свой `.claude/CLAUDE.md` рядом с кодом — он подгружается
при чтении файлов модуля и объясняет решения именно этого модуля.
