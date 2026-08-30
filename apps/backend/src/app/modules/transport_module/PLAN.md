# План модуля `transport_module`

## Цель

Создать модуль с HTTP-префиксом `/transport` для:

- учёта транспорта и его текущей комплектации;
- хранения истории аренды;
- определения текущего арендатора;
- привязки подписанного договора;
- полностью защищённого Admin JWT API.

## Принятые решения

- Денежные значения хранятся в CZK как `Numeric(12, 2)` / `Decimal`.
- `Transport.type` остаётся нормализованной строкой, не enum.
- Одна активная аренда разрешена одновременно для одного транспорта и одного
  курьера.
- Период аренды задаётся через `started_at` и `ended_at`.
- Администратор может вносить прошлые завершённые периоды.
- `is_active` не хранится: активность вычисляется как `ended_at IS NULL`.
- Пересекающиеся периоды запрещаются на уровне PostgreSQL exclusion
  constraints.
- Цена и комплектация аренды отдельно не фиксируются: историческим источником
  служит подписанный договор.
- Аренду нельзя редактировать или удалять обычным CRUD: только создать,
  завершить и приложить договор.
- Транспорт и курьер удаляются каскадно вместе с арендой, только если у неё нет
  подписанного договора.
- Подписанный договор блокирует удаление аренды, транспорта и курьера.
- Все endpoints помечаются `@authenticated`.
- События, фоновые задачи и настройки на первом этапе не нужны.

## Именование

Не использовать опечатки и неоднозначные названия:

| Исходное поле | Поле модуля |
| --- | --- |
| `number` | `serial_number` |
| `is_piedge` | `deposit_required` |
| `piedge_sum` | `deposit_amount` |
| `price` транспорта | `rental_price` |
| `price` комплектующего | `unit_price` |
| `count` | `quantity` |

## Модели

### Transport

Таблица `transports`.

| Поле | Тип | Правила |
| --- | --- | --- |
| `id` | UUIDv7 | PK, генерируется приложением |
| `type` | String(64) | trim, lowercase, обязательное |
| `model` | String(128) | trim, обязательное |
| `serial_number` | String(64) | trim, uppercase, unique |
| `color` | String(64) | trim, обязательное |
| `deposit_required` | Boolean | default `false` |
| `deposit_amount` | Numeric(12,2), nullable | только CZK |
| `rental_price` | Numeric(12,2) | больше нуля |
| `created_at` | timestamptz | серверное время |
| `updated_at` | timestamptz | серверное время |

Инварианты:

- при `deposit_required=false` значение `deposit_amount` должно быть `NULL`;
- при `deposit_required=true` сумма залога должна быть больше нуля;
- `serial_number` уникален после нормализации;
- удаление каскадно удаляет комплектацию и аренды без договора;
- `__patchable__` содержит все бизнес-поля, но не системные поля и связи;
- индекс `ix_transports_keyset(created_at DESC, id DESC)`.

### TransportComponent

Таблица `transport_components`.

| Поле | Тип | Правила |
| --- | --- | --- |
| `id` | UUIDv7 | PK |
| `transport_id` | UUID | FK на `transports`, `ON DELETE CASCADE` |
| `name` | String(128) | trim, обязательное |
| `unit_price` | Numeric(12,2) | неотрицательное |
| `quantity` | Integer | больше нуля |
| `created_at` | timestamptz | серверное время |
| `updated_at` | timestamptz | серверное время |

Дополнительно:

- итоговая стоимость вычисляется как `unit_price * quantity` и не хранится;
- ответ API содержит вычисленное поле `total_price`;
- название комплектующего уникально внутри одного транспорта;
- nested keyset-индекс:
  `(transport_id, created_at DESC, id DESC)`.

Комплектация представляет текущее состояние транспорта. Её изменения не
меняют PDF-договор, но меняют отображаемые структурированные данные прошлых
аренд.

### CourierTransport

Таблица `courier_transports`.

| Поле | Тип | Правила |
| --- | --- | --- |
| `id` | UUIDv7 | PK |
| `transport_id` | UUID | FK на `transports`, `ON DELETE CASCADE` |
| `courier_id` | UUID | строковый FK на `couriers`, без импорта Courier |
| `started_at` | timestamptz | обязательное aware datetime |
| `ended_at` | timestamptz, nullable | `NULL` означает активную аренду |
| `file_id` | UUID, nullable | уникальная ссылка на готовый `File` |
| `created_at` | timestamptz | дата создания записи |
| `updated_at` | timestamptz | дата изменения записи |

Инварианты:

- `ended_at > started_at`, если аренда завершена;
- будущие даты на первом этапе запрещены;
- `file_id` можно приложить при создании или позднее отдельной командой;
- один File нельзя использовать для нескольких аренд;
- приложенный договор нельзя заменить или отвязать;
- наружу отдаётся вычисляемое `is_active`;
- ORM relationship с Courier не создаётся, чтобы модули не импортировали друг
  друга;
- File импортируется через разрешённый `app.platform.files`.

## Пересечение аренд

Миграция подключает `btree_gist` и создаёт два exclusion constraint по
полуоткрытому диапазону `[started_at, ended_at)`:

- запрет пересечения периодов для одного `transport_id`;
- запрет пересечения периодов для одного `courier_id`.

Для активной аренды верхней границей считается `infinity`.

Это одновременно гарантирует:

- транспорт нельзя выдать двум курьерам;
- курьер не может арендовать два транспорта;
- закрытые исторические интервалы также не пересекаются;
- параллельные запросы не обходят ограничение.

Ошибки ограничений преобразуются в RFC 9457 `409 Conflict` с reason:

- `transport-rental-overlap`;
- `courier-rental-overlap`.

## Защита договора от удаления

Поскольку выбран условный каскад, потребуется DB-trigger:

- удаление `courier_transports` разрешено, если `file_id IS NULL`;
- удаление строки с `file_id IS NOT NULL` отклоняется именованной DB-ошибкой;
- каскадный DELETE Transport или Courier также останавливается этим trigger;
- сервисы преобразуют ошибку в `409 signed-contract-protects-rental`.

Потребуется узкое изменение `courier_module`: его DELETE должен преобразовывать
эту DB-ошибку в `Conflict`, не импортируя модели transport.

Удаление или перевод приложенного File в `deleting` также необходимо
блокировать до запуска S3 cleanup. Для этого потребуется согласованная проверка
в storage lifecycle; иначе storage может удалить объект раньше, чем FK
остановит удаление строки.

## API

Все ручки используют `@authenticated`. Пишущие ручки используют
`Depends(get_uow, scope="function")`, читающие — `get_ro_session`.

### Transport

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/transport` | создать транспорт |
| `GET` | `/transport` | keyset-список |
| `GET` | `/transport/{transport_id}` | транспорт, комплектация и активная аренда |
| `PATCH` | `/transport/{transport_id}` | изменить разрешённые поля |
| `DELETE` | `/transport/{transport_id}` | каскадно удалить, если нет подписанного договора |

Фильтры списка:

- `type`;
- `serial_number`;
- `courier_id`;
- `is_available`.

### Components

| Метод | Путь |
| --- | --- |
| `POST` | `/transport/{transport_id}/components` |
| `GET` | `/transport/{transport_id}/components` |
| `GET` | `/transport/{transport_id}/components/{component_id}` |
| `PATCH` | `/transport/{transport_id}/components/{component_id}` |
| `DELETE` | `/transport/{transport_id}/components/{component_id}` |

Каждый запрос ищет component одновременно по `transport_id` и `component_id`,
чтобы исключить доступ через чужой parent path.

### Rentals

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/transport/{transport_id}/rentals` | создать активную или завершённую историческую аренду |
| `GET` | `/transport/{transport_id}/rentals` | keyset-история |
| `GET` | `/transport/{transport_id}/rentals/{rental_id}` | одна аренда |
| `POST` | `/transport/{transport_id}/rentals/{rental_id}/close` | завершить активную аренду |
| `POST` | `/transport/{transport_id}/rentals/{rental_id}/contract` | приложить подписанный договор |

Обычные `PATCH` и `DELETE` для аренды отсутствуют.

## Идемпотентность

`@idempotent` применяется к:

- созданию Transport;
- созданию Component;
- созданию Rental;
- завершению Rental;
- прикреплению договора.

Эти endpoints требуют `Idempotency-Key`. `PATCH` и `DELETE` дополнительной
replay-защиты не требуют.

## Схемы

Request schemas:

- `TransportCreate`;
- `TransportPatch`;
- `TransportComponentCreate`;
- `TransportComponentPatch`;
- `CourierTransportCreate`;
- `CourierTransportClose`;
- `CourierTransportContractAttach`.

Response schemas:

- `TransportListItemResponse`;
- `TransportDetailResponse`;
- `TransportComponentResponse`;
- `CourierTransportResponse`;
- безопасная локальная проекция `FileResponse`.

Decimal сериализуется строкой, например `"1250.00"`, чтобы не терять точность.

## Структура файлов

```text
src/app/modules/transport_module/
  __init__.py
  AGENTS.md
  PLAN.md
  handlers.py
  module.py
  models/
    __init__.py
    transport.py
    component.py
    courier_transport.py
  schemas/
    __init__.py
    requests.py
    responses.py
  services/
    __init__.py
    common.py
    queries.py
    transports.py
    components.py
    rentals.py
```

Не создавать без реальной необходимости:

- `events.py`;
- `subscribers.py`;
- `tasks.py`;
- `consumers.py`;
- settings или lifespan.

Манифест:

- `name="transport_module"`;
- `prefix="/transport"`;
- router и models package;
- регистрация только через `src/app/modules/__init__.py::MODULES`.

## Миграция

Одна Alembic revision должна:

1. Подключить `btree_gist`.
2. Создать `transports`.
3. Создать `transport_components`.
4. Создать `courier_transports`.
5. Создать unique, check, keyset и parent-scoped индексы.
6. Создать exclusion constraints.
7. Создать trigger защиты подписанного договора.
8. Реализовать полный обратный `downgrade()`.

После генерации миграцию необходимо проверить вручную: autogenerate не создаст
корректно extension, exclusion constraints и trigger.

## Тесты

Файл `tests/test_transport_module.py` должен покрывать:

- `401` для каждого endpoint без Admin JWT;
- CRUD транспорта и комплектующих;
- запрет unknown fields и explicit `null`;
- точность Decimal и ограничения денежных значений;
- согласованность `deposit_required/deposit_amount`;
- уникальность серийного номера;
- nested resource isolation;
- keyset-пагинацию при одинаковом `created_at`;
- активную аренду для транспорта и курьера;
- исторические завершённые аренды;
- запрет пересекающихся интервалов;
- конкурентное создание конфликтующих аренд;
- завершение и повторное завершение аренды;
- READY-проверку File;
- запрет повторного использования и замены договора;
- каскадное удаление истории без договора;
- `409` при удалении Transport или Courier с договором;
- replay создающих операций через `Idempotency-Key`;
- наличие необходимых индексов и constraints.

## Проверка

```bash
uv run ruff format src/app/modules/transport_module tests/test_transport_module.py
make check
make test
uv run alembic check
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic check
```

Для тестов и миграции потребуется PostgreSQL через `infra/` и Docker.
