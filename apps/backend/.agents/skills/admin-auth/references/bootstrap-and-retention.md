# Bootstrap и retention

## Bootstrap первого Admin

API lifespan берёт transaction-scoped PostgreSQL advisory lock и проверяет
таблицу `admins` внутри той же транзакции:

- непустая таблица — no-op, bootstrap credentials больше не нужны;
- пустая таблица — обязательны валидные username и пароль 12–128 символов;
- несколько API replicas создают ровно одну строку;
- отсутствие credentials при пустой таблице роняет startup безопасной ошибкой;
- worker bootstrap не запускает.

Настройки:

```env
ADMIN_BOOTSTRAP_USERNAME=
ADMIN_BOOTSTRAP_PASSWORD=
ADMIN_BOOTSTRAP_TELEGRAM_ID=
ADMIN_REFRESH_COOKIE_NAME=admin_refresh
ADMIN_REFRESH_COOKIE_SECURE=false
ADMIN_REFRESH_COOKIE_SAMESITE=strict
ADMIN_REFRESH_CLEANUP_CRON=17 4 * * *
```

После первого успешного запуска bootstrap password нужно удалить из secret
store/.env. Compose передаёт `infra/.env` контейнеру через `env_file`.

## Retention и известные внешние меры

Периодическая TaskIQ-задача удаляет refresh rows только после `expires_at`.
Она зарегистрирована через `Module.tasks` и выполняется worker'ом.

Модуль не реализует rate limiting login. Перед публикацией admin API в
интернет ограничение попыток должно обеспечиваться ingress/API gateway либо
отдельным согласованным механизмом с распределённым состоянием. Не добавляй
локальный in-memory limiter: он обходится несколькими uvicorn replicas и
теряет состояние при рестарте.
