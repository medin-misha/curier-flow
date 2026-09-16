# Модуль `documents`

Применяются [root](../../../../../../AGENTS.md) и [backend](../../../../AGENTS.md)
правила; читай их, если ещё не загружены.

Модуль владеет неизменяемыми DOCX-шаблонами и ресурсом
`/document-templates`. Исходник всегда является подтверждённым
`app.platform.files.File`; сгенерированный документ транзиентен и не создаёт
ни File, ни отдельную доменную строку.

Критичные инварианты:

- все endpoints защищены `@authenticated`;
- создание принимает `ready` DOCX `file_id`, скачивает его только после
  закрытия читающей DB-сессии и сохраняет извлечённые поля короткой отдельной
  транзакцией;
- синтаксис ограничен `{group.field}`, значения только строковые, а набор
  входных ключей обязан точно совпасть со схемой шаблона;
- шаблон не патчится; точный повтор `name + file_id` возвращает существующую
  строку, другое имя для занятого File даёт конфликт;
- пока шаблон существует, DB запрещает удалить File или перевести его в
  `deleting`; DELETE шаблона не удаляет File;
- список использует keyset `(created_at DESC, id DESC)`;
- DOCX ZIP/XML разбирается с пределами размера и числа entries, без DTD,
  entities, symlink, path traversal и macro-enabled package.

Карта: `handlers.py` содержит HTTP, `services.py` — DB/S3 orchestration,
`docx.py` — чистый parser/renderer, `models/` и `schemas/` — хранилище и
контракт, `module.py` — lifespan и манифест. Проверка из `apps/backend/`:

```bash
uv run ruff format src/app/modules/documents tests/test_documents.py
make check
make test
uv run alembic check
```
