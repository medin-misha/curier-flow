# MFS Fleet — Vue.js

Публичный сайт перенесён из проекта OpenDesign
`dade07cf-8d90-4d69-9b73-4c1817465c7c`, исходник `mfs-fleet.html`.
Сохранены макет, фирменные SVG, локальные шрифты, RU/CZ/EN, темы и адаптивность.
Стек: Vue 3 + TypeScript + Vite; в контейнере статику и API обслуживает nginx.
Архив прежнего Next.js-сайта не используется сборкой.

## Весь стек

Из корня репозитория:

```bash
make up
```

Сайт: https://localhost, анкета: https://localhost/form.
Команда делегирует запуск `make -C infra up`: инфраструктура, logging,
миграции, backend, сайт и админ-панель. Подготовка окружения, Grafana secret и
локального HTTPS: [infra/README.md](../../infra/README.md).

После изменения кода: `make -C infra reboot-apps`.

## Локальная разработка и предпросмотр

Из `apps/frontend-site/`:

```bash
npm ci
npm run dev
```

http://127.0.0.1:3000. Для API нужен запущенный стек. Vite по умолчанию
проксирует `/api` в https://backend.localhost. После экспорта Caddy CA:

```bash
make -C ../../infra caddy-ca
NODE_EXTRA_CA_CERTS=../../infra/secrets/caddy-root.crt npm run dev
```

Другой backend можно задать через `BACKEND_API_URL` в `.env.local`.
Настройки Vite не влияют на Docker: там proxy всегда направлен на `api:8000`.

```bash
npm run build
NODE_EXTRA_CA_CERTS=../../infra/secrets/caddy-root.crt npm run preview
```

## Проверка

```bash
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
make -C ../../infra check
E2E_BASE_URL=https://localhost E2E_LIVE=1 npm run test:e2e
```

Обычный browser-suite проверяет форму с mock API; последний сценарий отправляет
синтетическую анкету в живой backend и проверяет повтор без создания дубликата.
Результаты и screenshots сохраняются в игнорируемом `test-results/`.

## Контракт формы

`POST /api/courier` → `POST /courier`: JSON-строка `payload`, затем части `files`
в порядке массива `documents`. При 201 показывается получение заявки, при 200
— существующая анкета без обновления документов. Ошибки и timeout сохраняют
введённые поля для повтора. Персональные данные остаются только в памяти страницы.

Email вводится полностью; автоматическое добавление `@gmail.com` убрано.
Выбор транспорта удалён по согласованию: API не поддерживает это поле.
Ограничения обработки документов: [docs/known-gaps.md](docs/known-gaps.md).
