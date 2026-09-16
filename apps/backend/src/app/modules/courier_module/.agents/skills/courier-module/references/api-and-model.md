# API и модели

Префикс `/courier`. Полные aggregates возвращают только POST корня, GET item и
GET list; отдельных nested GET нет. Список — keyset по
`(created_at DESC, id DESC)` и точные фильтры email/phone/full_name/status;
`status` выбирает Courier с хотя бы одной platform-регистрацией в этом статусе.

`POST /courier` публичен для формы регистрации. Каждый другой endpoint router
помечен `@authenticated` и требует Admin access JWT; защита не распространяется
на `/files` и не задаётся общим URL-списком.

Courier владеет accounts/documents через `delete-orphan` и DB cascade. Document
имеет однонаправленный joined relationship к platform `File`; у File нет
backref. Aggregate query всегда явно загружает accounts и
documents->file и исключает `File.status=deleting`.

Обычные writes используют function-scoped UoW. Nested id всегда проверяется
вместе с `courier_id`. PATCH нормализует email/phone, поддерживает consent
transitions и разрешает explicit null только nullable-полям.

`POST /courier` сознательно без `@idempotent`: гарантию дают natural keys и
ON CONFLICT, а multipart orchestration не является одной UoW/JSON-транзакцией.
POST Document также многофазный и не использует текущую JSON/UoW обвязку;
повтор считается отдельным бизнес-документом.

## Массовые операции

`POST /courier/bulk-delete` принимает `{"courier_ids": ["UUID", ...]}`.
`PATCH /courier/bulk-status` принимает тот же список и обязательные `platform`
(`bolt_food`, `foodora`, `wolt`) и `status` (`pending`, `active`, `inactive`).
Статус принадлежит platform account, не самому Courier; остальные платформы
не меняются, отсутствующие регистрации автоматически не создаются.

Обе ручки требуют Admin access JWT и `Idempotency-Key`. Список содержит от 1
до 100 уникальных UUID; пустой список, дубликаты и неверные значения дают 422.
Операции синхронны и атомарны: одна function-scoped UoW на всю пачку, курьеры
блокируются в порядке UUID. Статические пути объявляются до `/{courier_id}`.

- Не найден Courier: 404 с `courier_ids` отсутствующих курьеров.
- Нет выбранного account: 409 `reason=platform-account-missing`, `platform`
  и `courier_ids` курьеров без регистрации.
- Удаление запрещено договором: 409 `reason=signed-contract-protects-rental`
  и `courier_id` первого заблокированного курьера в порядке UUID.
- Любая ошибка откатывает всю пачку, файловые статусы и Idempotency-Key.
- Удаление возвращает 200 `{"deleted_count": N}`. S3 очищается позднее.
- Смена статуса возвращает 200 `{"updated_count": N, "unchanged_count": M}`;
  уже нужный статус не меняет `updated_at` и входит в `unchanged_count`.
- Повтор с тем же ключом и тем же телом возвращает исходный ответ, включая
  счётчики; другое тело с занятым ключом даёт 409 `payload-mismatch`.
