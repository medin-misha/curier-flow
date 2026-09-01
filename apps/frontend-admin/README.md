# MFS Frontend Admin

Vue 3-панель для работы с реестром курьеров May Fleet Solutions. Панель
аутентифицирует администратора и работает с существующими Admin и Courier API.

## Запуск в Docker Compose

Единственная точка управления контейнерами находится в `infra/`:

```bash
make -C infra up
make -C infra caddy-ca
```

Админка откроется по адресу `https://admin.localhost`. Caddy завершает TLS, а
nginx внутри frontend-контейнера сохраняет same-origin контракт и проксирует
API по внутреннему адресу `http://api:8000`. Не задавайте `VITE_API_URL` для
Compose-сборки: refresh cookie привязана к `admin.localhost`.

Root CA для доверия локальным сертификатам экспортируется в
`infra/secrets/caddy-root.crt`; процедура установки описана в backend README.

## Отдельный Vite dev-сервер

```bash
cd apps/frontend-admin
npm install
npm run dev
```

Vite откроет приложение по адресу `http://127.0.0.1:5173`. Этот режим не входит
в стандартный Compose-стек: его proxy ожидает отдельно доступный API на
`http://127.0.0.1:8000`, тогда как Compose публикует API только через Caddy.

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
- просмотр профиля, изменение статусов платформ и скачивание документов курьера;
- создание курьера и опционального документа через multipart API;
- редактирование и удаление курьера;
- состояния загрузки и ошибки API;
- управление модальными окнами с клавиатуры.

Access JWT хранится только в памяти приложения. Refresh-токен недоступен
JavaScript и передаётся backend только через HttpOnly cookie.
