# Публичный сайт MFS Fleet

Vue 3, TypeScript, Vite. Применяются [общие правила](../../AGENTS.md).
Команды запускай из `apps/frontend-site/`, контейнеры — через `infra/`.

## Команды

- `npm ci` — зависимости.
- `npm run dev` / `npm run preview` — локально на порту 3000.
- `npm run typecheck`, `npm test`, `npm run build` — проверка и сборка.
- `npm run test:e2e` — Chromium desktop/mobile, mock API.
- `E2E_BASE_URL=https://localhost E2E_LIVE=1 npm run test:e2e` — живой стек;
  создаёт одну синтетическую анкету, повторяет запрос и проверяет дубликат.

## Инварианты

- Исходный макет OpenDesign перенесён в Vue SFC: структура в `src/components`,
  тексты RU/CZ/EN в `src/content`, локальные шрифты и графика в `public/assets`.
- Сохраняй исходные SVG, токены и адаптивность в `src/styles/mfs-design.css`.
- `src/features/application/application.ts` — валидация и multipart-контракт.
  Публичная ручка: `POST /api/courier` → backend `POST /courier`.
- Порядок `documents` совпадает с `files`. Чехия: две стороны identity_card;
  другие гражданства: passport и residence_permit.
- Успех показывается только после 200/201 с id. 200 означает существующую
  анкету без обновления документов; сетевые ошибки сохраняют введённые данные.
- Не сохраняй персональные данные/файлы в localStorage, cookies или логах.
- Клиентская валидация файлов — UX; ограничения серверной защиты и privacy
  описаны в [docs/known-gaps.md](docs/known-gaps.md).
- `/form`, `/apply` и старый `#/form` должны работать. Прямая ссылка на экран
  успеха без подтверждённого ответа сервера возвращает к форме.
- После изменений формы проверяй transport-тесты, desktop/mobile, клавиатуру,
  dark mode, RU/CZ/EN и отсутствие ошибок консоли.
