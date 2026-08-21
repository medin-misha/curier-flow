---
name: storage-module
description: "Изменить существующий backend-модуль storage: presigned upload/download, подтверждение, статусы файлов, S3, удаление, фоновые задачи или тесты. Применяй для любых правок apps/backend/src/app/modules/storage/."
---

# Работа с модулем storage

Сначала прочитай `../../../AGENTS.md` модуля и backend-правила, соответствующие
изменяемым файлам.

Выбери только нужный контекст:

- контракт ручек → [endpoints.md](references/endpoints.md);
- запрет проксирования → [direct-transfer.md](references/direct-transfer.md);
- статусы и гонки → [lifecycle.md](references/lifecycle.md);
- S3 и границы транзакций → [transactions.md](references/transactions.md);
- internal/public endpoint и SigV4 →
  [presigned-links.md](references/presigned-links.md);
- генерация ключа → [object-key.md](references/object-key.md);
- confirm и фактические проверки → [confirmation.md](references/confirmation.md);
- `FileConfirmed` → [events.md](references/events.md);
- периодическая уборка → [cleanup-tasks.md](references/cleanup-tasks.md);
- индексы → [indexes.md](references/indexes.md);
- ручная проверка → [commands.md](references/commands.md).

Для событий и задач используй также `background-effect`, для схемы БД —
`db-migration`. Перед завершением прочитай
[change-checklist.md](references/change-checklist.md) и выполни
`uv run pytest tests/test_storage.py -v` из `apps/backend/`.
