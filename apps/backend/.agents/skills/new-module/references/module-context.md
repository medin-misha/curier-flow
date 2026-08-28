## Шаг 13. Контекст модуля

`src/app/modules/<name>/AGENTS.md` обязателен — без него падает
`tests/test_architecture.py::test_every_module_carries_agent_instructions`.

Держи этот файл коротким: ориентир 1–3 КБ. В обязательный контекст входят только:

1. требование прочитать корневой `AGENTS.md` и `apps/backend/AGENTS.md`, потому
   что ближайший module AGENT не объединяется с ними автоматически;
2. назначение и границы модуля;
3. один-два критичных инварианта, которые нельзя безопасно вывести из кода;
4. минимальная карта файлов и команды проверки;
5. ссылка на локальный skill, если подробных сценариев много.

Не переноси в `AGENTS.md` таблицы всех ручек, полный жизненный цикл, каталог событий,
индексов и примеров запросов. Для сложного модуля создай
`src/app/modules/<name>/.agents/skills/<name>-module/SKILL.md`, а подробности разложи по
`references/*.md`. В `SKILL.md` явно укажи, какой reference читать для каждого типа задачи.

Образцы: `src/app/modules/storage/AGENTS.md` с локальным `storage-module` и
`src/app/modules/health/AGENTS.md` с локальным `health-module`.
