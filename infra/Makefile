# Управление стеком. Перед первым запуском: cp infra/.env.example infra/.env

.DEFAULT_GOAL := help
.PHONY: help check ps \
	up up-all up-infra migrate up-apps \
	reboot reboot-all reboot-infra reboot-apps \
	down down-all down-infra down-apps \
	delete delete-all delete-infra delete-apps

# Каталог Makefile, а не текущий: цели должны работать и из корня через -C.
HERE := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))

INFRA := docker compose -f $(HERE)/docker-compose.infra.yml
APPS  := docker compose -f $(HERE)/docker-compose.apps.yml
APPS_WITH_TELEGRAM := $(APPS) --profile telegram

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

check: ## Проверить compose-файлы и контекст агента
	$(INFRA) config --quiet
	$(APPS) config --quiet
	../scripts/check-agent-context.sh

ps: ## Показать состояние инфраструктуры и приложений
	$(INFRA) ps
	$(APPS_WITH_TELEGRAM) ps

up: up-all ## Поднять весь стек: инфраструктура, миграции, приложения

up-all: ## Инфраструктура до healthy, затем миграции и приложения
	$(MAKE) up-infra
	$(MAKE) migrate
	$(MAKE) up-apps

up-infra: ## Поднять инфраструктуру и дождаться healthy
	$(INFRA) up -d --wait
	$(INFRA) run --rm minio-init

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

reboot-infra: ## Пересоздать контейнеры инфраструктуры
	$(MAKE) down-infra
	$(MAKE) up-infra

reboot-apps: ## Пересобрать и пересоздать приложения
	$(MAKE) down-apps
	$(MAKE) up-apps

down: down-all ## Остановить весь стек, данные сохраняются

# Приложения первыми: пока их контейнеры в сети curier-flow, её не удалить.
down-all: ## Остановить приложения, затем инфраструктуру
	$(MAKE) down-apps
	$(MAKE) down-infra

down-infra: ## Остановить инфраструктуру, volume'ы сохраняются
	$(INFRA) down

down-apps: ## Остановить приложения
	$(APPS_WITH_TELEGRAM) down

delete: delete-all ## Снести весь стек вместе с данными

delete-all: ## Удалить контейнеры, сети и ВСЕ данные
	@printf 'Удалить контейнеры и все данные (postgres, rabbitmq, redis, minio)? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(APPS_WITH_TELEGRAM) down --volumes --remove-orphans
	$(INFRA) down --volumes --remove-orphans

delete-infra: ## Удалить инфраструктуру вместе с данными
	@printf 'Удалить данные postgres, rabbitmq, redis, minio? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(INFRA) down --volumes --remove-orphans

delete-apps: ## Удалить контейнеры приложений и их образы
	$(APPS_WITH_TELEGRAM) down --rmi local --remove-orphans
