# Контекст Codex в репозитории

Основание: официальные документы Codex про
[цепочку AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
и [progressive disclosure skills](https://learn.chatgpt.com/docs/build-skills).

## Основная модель

Одна сессия Codex обслуживает одну основную область. При старте Codex собирает
`AGENTS.md` от корня репозитория до рабочего каталога, а project skills — из
`.agents/skills` рабочего каталога и его родителей. Последующий `cd` не
заменяет уже собранный контекст.

## Как запускать задачи

```bash
codex --cd .                                             # весь репозиторий
codex --cd apps/backend                                  # backend
codex --cd apps/backend/src/app/modules/storage          # storage
codex --cd apps/backend/src/app/modules/health           # health
codex --cd apps/telegram-bot                             # Telegram bot worker
codex --cd infra                                         # compose и стек
```

Для будущего сервиса используй `codex --cd apps/<service>` и положи рядом его
`AGENTS.md` и `.agents/skills/`.

## Межсервисные изменения

1. Из корня определить контракт и части изменения.
2. Реализовать каждую часть в отдельной service-scoped сессии.
3. Выполнить интеграционную проверку из корня или `infra/`.

Так backend-сессия не получает skills соседних сервисов, а контекст модулей не
накапливается в одном длинном диалоге.

## Что где хранится

| Информация | Место |
| --- | --- |
| обязательна для любой работы в области | ближайший `AGENTS.md` |
| повторяемый рабочий процесс | `.agents/skills/<name>/SKILL.md` |
| подробность только для одного режима skill | `references/*.md` внутри skill |
| детерминированная повторяемая операция | `scripts/` внутри skill |
| общая проверяемая политика backend | `apps/backend/.agents/rules/` |

`AGENTS.md` должен быть маршрутизатором и набором критических инвариантов, а
не полной документацией системы. `SKILL.md` хранит общую последовательность и
выбирает references; он не дублирует их.

## Бюджеты

- корневой `AGENTS.md`: до 4 KiB;
- root + service: до 12 KiB;
- root + service + module: до 20 KiB;
- основной `SKILL.md`: до 12 KiB.

Предел Codex для project instructions по умолчанию выше, но запас нужен для
роста и более близких инструкций. Бюджеты и ссылки проверяет
`scripts/check-agent-context.sh`.

## Новый backend-модуль

Запусти Codex из `apps/backend` и используй `new-module`. Созданный модуль
получает короткий `AGENTS.md`; локальный skill добавляется только когда у
модуля появляется собственный повторяемый и нетривиальный workflow.

## Новый сервис

1. Создай `apps/<service>/AGENTS.md` с командами, инвариантами и ссылками.
2. Положи service-specific skills в `apps/<service>/.agents/skills/`.
3. Оставь общерепозиторные skills в корневом `.agents/skills/`.
4. Добавь команду запуска в корневой `AGENTS.md` и этот документ.
5. Добавь service chain в проверку контекстного бюджета.
