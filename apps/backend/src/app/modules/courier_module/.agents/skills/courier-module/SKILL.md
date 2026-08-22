---
name: courier-module
description: Изменить существующий courier_module: aggregate multipart upload, Courier/accounts/documents CRUD, relationships, deletion или retention.
---

# Courier module

Рабочий каталог команд — `apps/backend/`. Сначала прочитай `AGENTS.md` модуля
и только подходящий reference:

- aggregate POST, staging, natural-key race или S3 —
  `references/aggregate-upload.md`;
- ORM, API, PATCH, nested resources — `references/api-and-model.md`;
- DELETE, File lifecycle или retention — `references/retention-and-deletion.md`.

При фоновой работе дополнительно используй backend skill `background-effect`.
При изменении таблиц существующего модуля — `db-migration`. Перед коммитом —
`pre-commit`, затем `git-commit`.

Не импортируй storage, не добавляй обратный Courier relationship в File, не
читай UploadFile без bounded size и не вызывай S3 при открытой транзакции.
