# Управление стеком. Перед первым запуском: cp infra/.env.example infra/.env

.DEFAULT_GOAL := help
.PHONY: help check ps \
	up up-all up-infra up-logging migrate up-apps \
	reboot reboot-all reboot-infra reboot-logging reboot-apps \
	down down-all down-infra down-logging down-apps \
	delete delete-all delete-infra delete-logging delete-apps

# Каталог Makefile, а не текущий: цели должны работать и из корня через -C.
HERE := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))

INFRA := docker compose -f $(HERE)/docker-compose.infra.yml
APPS  := docker compose -f $(HERE)/docker-compose.apps.yml
LOGGING := docker compose -f $(HERE)/docker-compose.logging.yml
APPS_WITH_TELEGRAM := $(APPS) --profile telegram

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

check: ## Проверить compose-файлы и контекст агента
	$(INFRA) config --quiet
	$(LOGGING) config --quiet
	$(APPS) config --quiet
	../scripts/check-agent-context.sh

ps: ## Показать состояние инфраструктуры, logging и приложений
	$(INFRA) ps
	$(LOGGING) ps
	$(APPS_WITH_TELEGRAM) ps

up: up-all ## Поднять весь стек: инфраструктура, logging, миграции, приложения

up-all: ## Инфраструктура, logging, миграции и приложения
	$(MAKE) up-infra
	$(MAKE) up-logging
	$(MAKE) migrate
	$(MAKE) up-apps

up-infra: ## Поднять инфраструктуру и дождаться healthy
	$(INFRA) up -d --wait
	$(INFRA) run --rm minio-init

up-logging: ## Поднять Grafana, логи и метрики
	@test -s $(HERE)/secrets/grafana_admin_password || { \
		printf '%s\n' 'Нет infra/secrets/grafana_admin_password; создайте его по инструкции в infra/.env.example.'; \
		exit 1; \
	}
	$(LOGGING) up -d --wait

migrate: ## Собрать образ API и применить миграции без запуска uvicorn
	$(APPS) run --rm --build --no-deps api alembic upgrade head

up-apps: ## Собрать образы и поднять приложения
	@if $(APPS) config --environment | grep -q '^TELEGRAM_BOT_TOKEN=.'; then \
		$(APPS_WITH_TELEGRAM) up -d --build --wait; \
	else \
		printf '%s\n' 'Предупреждение: Telegram worker пропущен: TELEGRAM_BOT_TOKEN пуст; задайте его в infra/.env или shell-окружении и повторите запуск.'; \
		$(APPS) up -d --build --wait; \
	fi

# down+up, а не `docker compose restart`: restart поднимает старые контейнеры
# со старым образом и окружением, правки в compose и .env до сервиса не доедут.
reboot: reboot-all ## Перезапустить весь стек

reboot-all: ## Пересоздать все контейнеры, данные сохраняются
	$(MAKE) down-all
	$(MAKE) up-all


# Apps и logging подключены к сети curier-flow, которой владеет infra-проект.
# Их нужно снять до удаления сети и вернуть после пересоздания инфраструктуры.
reboot-infra: ## Пересоздать инфраструктуру и подключённые к ней сервисы
	$(MAKE) down-apps
	$(MAKE) down-logging
	$(MAKE) down-infra
	$(MAKE) up-infra
	$(MAKE) up-logging
	$(MAKE) migrate
	$(MAKE) up-apps

reboot-logging: ## Пересоздать контейнеры logging
	$(MAKE) down-logging
	$(MAKE) up-logging

reboot-apps: ## Пересобрать и пересоздать приложения
	$(MAKE) down-apps
	$(MAKE) up-apps

down: down-all ## Остановить весь стек, данные сохраняются

# Приложения и logging первыми: пока они в сети curier-flow, её не удалить.
down-all: ## Остановить приложения, logging, затем инфраструктуру
	$(MAKE) down-apps
	$(MAKE) down-logging
	$(MAKE) down-infra

down-infra: ## Остановить инфраструктуру, volume'ы сохраняются
	$(INFRA) down

down-logging: ## Остановить logging, volume'ы сохраняются
	$(LOGGING) down

down-apps: ## Остановить приложения
	$(APPS_WITH_TELEGRAM) down

delete: delete-all ## Снести весь стек вместе с данными

delete-all: ## Удалить контейнеры, сети и ВСЕ данные
	@printf 'Удалить контейнеры и все данные (infra и observability)? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(APPS_WITH_TELEGRAM) down --volumes --remove-orphans
	$(LOGGING) down --volumes --remove-orphans
	$(INFRA) down --volumes --remove-orphans

delete-infra: ## Удалить инфраструктуру вместе с данными
	@printf 'Удалить данные postgres, rabbitmq, redis, minio? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(APPS_WITH_TELEGRAM) down
	$(LOGGING) down
	$(INFRA) down --volumes --remove-orphans

delete-logging: ## Удалить logging вместе с метриками, логами и Grafana
	@printf 'Удалить данные Grafana, Loki, Prometheus и Alloy? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(LOGGING) down --volumes --remove-orphans

delete-apps: ## Удалить контейнеры приложений и их образы
	$(APPS_WITH_TELEGRAM) down --rmi local --remove-orphans
