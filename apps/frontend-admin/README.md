# MFS Frontend Admin

Vue 3-панель для работы с реестром курьеров May Fleet Solutions. Панель
аутентифицирует администратора и работает с существующими Admin и Courier API.

## Локальный запуск

```bash
cd apps/frontend-admin
npm install
npm run dev
```

Vite откроет приложение по адресу `http://127.0.0.1:5173`. В dev-режиме
запросы `/admin` и `/courier` проксируются на `http://127.0.0.1:8000`.

Если API публикуется на отдельном origin и окружение разрешает такие запросы,
его можно задать во время сборки:

```bash
VITE_API_URL=https://api.example.com npm run build
```

Для refresh-сессии предпочтителен same-origin reverse proxy, сохраняющий пути
`/admin/auth/*`: backend устанавливает HttpOnly cookie с
`Path=/admin/auth`.

## Проверка

```bash
npm run typecheck
npm test
npm run build
npm run preview
```

Команда `npm run preview` запускает собранную версию по адресу
`http://127.0.0.1:4173`.

## Текущие возможности

- вход, восстановление refresh-сессии и выход администратора;
- автоматическое обновление access JWT после ответа `401`;
- точный поиск и keyset-пагинация реестра;
- адаптивное представление таблицы;
- просмотр профиля, платформ и документов курьера;
- создание курьера и опционального документа через multipart API;
- редактирование и удаление курьера;
- состояния загрузки и ошибки API;
- управление модальными окнами с клавиатуры.

Access JWT хранится только в памяти приложения. Refresh-токен недоступен
JavaScript и передаётся backend только через HttpOnly cookie.
