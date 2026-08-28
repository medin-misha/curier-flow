# API и модели

Префикс `/courier`. Полные aggregates возвращают только POST корня, GET item и
GET list; отдельных nested GET нет. Список — keyset по
`(created_at DESC, id DESC)` и точные фильтры email/phone/full_name.

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
