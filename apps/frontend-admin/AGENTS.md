# MFS Frontend Admin

Vue 3 + Vite админ-панель для аутентификации и работы с реестром курьеров.
Пользовательский интерфейс и сообщения об ошибках — по-русски.

Применяются [общие правила](../../AGENTS.md); прочитай их, если ещё не загружены.

## Команды

| Команда | Что делает |
| --- | --- |
| `npm run dev` | локальный Vite-сервер на `127.0.0.1:5173` |
| `npm run typecheck` | проверка Vue и TypeScript |
| `npm test` | тесты Vitest + jsdom |
| `npm run build` | typecheck и production-сборка |

## Границы

- `src/api/` владеет HTTP-контрактом, авторизацией и преобразованием ответов;
- `src/composables/` владеет состоянием сценариев и сессии;
- `src/components/` содержит представление и пользовательские взаимодействия;
- `src/types/` содержит публичные типы frontend-контракта.

Access JWT хранится только в памяти. Refresh token остаётся HttpOnly cookie с
`Path=/admin/auth`; не переносить его в JavaScript-хранилища. В production
запросы `/admin` и `/courier` идут через same-origin nginx proxy. В dev и
preview тот же контракт обеспечивает Vite proxy.

Перед завершением изменения выполни `npm run typecheck`, `npm test` и
`npm run build`. Не ослабляй тесты ради прохождения проверки.
