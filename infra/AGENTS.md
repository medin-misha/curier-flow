# Инфраструктура

Каталог `infra/` — единственная точка запуска и управления контейнерами.
Для инфраструктурных задач используй его как рабочий каталог и перед работой
прочитай корневой `../AGENTS.md`: локальный файл дополняет общие правила, но не
рассчитывай на их автоматическое объединение.

## Файлы

- `docker-compose.infra.yml` — PostgreSQL, RabbitMQ, Redis и MinIO;
- `docker-compose.apps.yml` — процессы приложений; Telegram worker вынесен в
  опциональный Compose profile;
- `docker-compose.logging.yml` — Caddy, Grafana, Loki, Alloy, Prometheus и
  exporters;
- `observability/` — provisioned dashboards, правила и конфигурации сборщиков;
- `.env.example` — единый документированный контракт окружения стека;
- `Makefile` — публичный интерфейс операций.

## Правила

- Перед командой прочитай актуальные цели через `make help`.
- `up` поднимает инфраструктуру и logging до healthy, затем одноразовым
  контейнером API применяет Alembic-миграции и запускает приложения.
- `migrate` собирает образ API и переопределяет его command на
  `alembic upgrade head`; uvicorn и API lifespan при этом не запускаются.
- `up` и `up-apps` включают Telegram profile только при непустом
  `TELEGRAM_BOT_TOKEN`, разрешённом Compose из `infra/.env` и shell-окружения;
  пустое значение даёт предупреждение и не создаёт контейнер.
- Для применения кода приложения используй `make reboot-apps`, а не
  `docker compose restart`: нужен новый образ и окружение.
- При остановке приложения идут раньше logging, а logging раньше
  инфраструктуры; lifecycle-команды всегда охватывают Telegram profile, даже
  если token после запуска удалён.
- `delete*` удаляет данные или образы и требует явного подтверждения; не
  подменяй его неинтерактивной командой.
- Новая переменная одновременно появляется в `.env.example`, compose и
  настройках владельца; секреты и локальный `.env` не коммитятся.
- Healthcheck приложения проверяет `/health/live`, не `/health/ready`.
- Caddy — единственный публичный HTTP ingress: внешние URL используют HTTPS, а
  upstream-адреса внутри Compose остаются HTTP.
- Локальный Caddy CA хранится в volume и сохраняется при `down`/`reboot`;
  `delete-logging` удаляет его и требует заново установить доверенный root.

После изменения используй skill `infra-check`. Для backend-кода начни
отдельную сессию с рабочим каталогом `apps/backend/`.
