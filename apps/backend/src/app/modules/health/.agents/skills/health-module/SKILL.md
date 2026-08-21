---
name: health-module
description: "Изменить существующий backend-модуль health: liveness, readiness, dependency probes, /health/info или их тесты. Применяй для любых правок apps/backend/src/app/modules/health/."
---

# Работа с модулем health

Сначала прочитай `../../../AGENTS.md` модуля и backend-правила, соответствующие
изменяемым файлам.

Выбери только нужный контекст:

- контракт ручек → [endpoints.md](references/endpoints.md);
- live против ready → [readiness.md](references/readiness.md);
- состав файлов → [layout.md](references/layout.md);
- lifespan и границы слоя → [architecture.md](references/architecture.md);
- проверки БД, RabbitMQ и S3 →
  [dependency-probes.md](references/dependency-probes.md);
- статус, тело и кеширование readiness →
  [response-contract.md](references/response-contract.md);
- публичность `/health/info` → [security.md](references/security.md);
- ручная проверка → [commands.md](references/commands.md).

Перед завершением прочитай
[change-checklist.md](references/change-checklist.md) и выполни
`uv run pytest tests/test_health.py -v` из `apps/backend/`.
