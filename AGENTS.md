# О проекте

CRM для чешских курьерских флотилий-посредников: лиды, договоры, автопарк и
расходы для Bolt, Foodora и Wolt. Включает публичный лендинг с мастером заявки,
UI управления Admin/Courier и Telegram-уведомления.

## Выбор области работы

OpenCode применяет ближайший `AGENTS.md`; родительские файлы не объединяются,
поэтому вложенный файл явно ссылается на root. Project skills из
`.agents/skills/` ищутся по пути до корня worktree.

Выбери рабочий каталог по области задачи:

| Задача | Рабочий каталог |
| --- | --- |
| архитектура, аудит, координация сервисов | корень репозитория |
| backend или новый backend-модуль | `apps/backend/` |
| существующий backend-модуль | `apps/backend/src/app/modules/<name>/` |
| public landing/application wizard | `apps/frontend-site/` |
| Admin/Courier management UI | `apps/frontend-admin/` |
| Telegram bot worker | `apps/telegram-bot/` |
| Docker Compose и окружение | `infra/` |

Межсервисную задачу разложи из root, части реализуй в service-scoped сессиях,
а интеграцию проверь из root или `infra/`.

## Карта репозитория

- `apps/backend/` — FastAPI backend ([правила](apps/backend/AGENTS.md));
- `apps/frontend-site/` — public landing/application wizard
  ([правила](apps/frontend-site/AGENTS.md));
- `apps/frontend-admin/` — Admin/Courier management UI
  ([правила](apps/frontend-admin/AGENTS.md));
- `apps/telegram-bot/` — worker Telegram-уведомлений
  ([правила](apps/telegram-bot/AGENTS.md));
- `infra/` — контейнеры и окружение ([правила](infra/AGENTS.md)).

## Что где хранится

| Что | Где |
| --- | --- |
| router и критические инварианты области | ближайший `AGENTS.md` |
| повторяемый workflow | `.agents/skills/<name>/SKILL.md` |
| progressive disclosure режима | `references/*.md` внутри skill |
| детерминированная операция | `scripts/` внутри skill |
| общая backend policy | `apps/backend/.agents/rules/` |

`SKILL.md` задаёт общий порядок и выбирает references, не дублируя их.

## Бюджеты

- root `AGENTS.md` — до 4 KiB;
- root + service — до 12 KiB;
- root + service + module — до 20 KiB;
- `SKILL.md` — до 12 KiB.

`scripts/check-agent-context.sh` проверяет бюджеты, цепочки и Markdown-ссылки
на `references/*.md` из skills.

## Новый сервис

1. Создай `apps/<service>/AGENTS.md` со ссылкой на root, командами и
   инвариантами сервиса.
2. Service skills добавляй только для повторяемого workflow; общие оставляй в
   корневом `.agents/skills/`.
3. Зарегистрируй рабочую область и сервис в корневой карте.
4. Добавь service chain в `scripts/check-agent-context.sh`.

## Общие правила

- Комментарии и документация — по-русски; имена кода, ключи логов и топики —
  по-английски.
- Контейнерами управляй только через `infra/`; актуальные команды показывает
  `make -C infra help`.
- Не смешивай изменения разных сервисов в один коммит без общей причины.
- Для коммитов используй скилл `git-commit`.
