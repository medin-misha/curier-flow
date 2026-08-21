# Управление стеком. Перед первым запуском: cp infra/.env.example infra/.env

.DEFAULT_GOAL := help
.PHONY: help check \
	up up-all up-infra up-apps \
	reboot reboot-all reboot-infra reboot-apps \
	down down-all down-infra down-apps \
	delete delete-all delete-infra delete-apps

# Каталог Makefile, а не текущий: цели должны работать и из корня через -C.
HERE := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))

INFRA := docker compose -f $(HERE)/docker-compose.infra.yml
APPS  := docker compose -f $(HERE)/docker-compose.apps.yml

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

check: ## Проверить compose-файлы и контекст агента
	$(INFRA) config --quiet
	$(APPS) config --quiet
	../scripts/check-agent-context.sh

up: up-all ## Поднять весь стек

up-all: up-infra up-apps ## Инфраструктура до healthy, затем приложения

up-infra: ## Поднять инфраструктуру и дождаться healthy
	$(INFRA) up -d --wait
	$(INFRA) run --rm minio-init

up-apps: ## Собрать образы и поднять приложения
	$(APPS) up -d --build --wait

# down+up, а не `docker compose restart`: restart поднимает старые контейнеры
# со старым образом и окружением, правки в compose и .env до сервиса не доедут.
reboot: reboot-all ## Перезапустить весь стек

reboot-all: down-all up-all ## Пересоздать все контейнеры, данные сохраняются

reboot-infra: down-infra up-infra ## Пересоздать контейнеры инфраструктуры

reboot-apps: down-apps up-apps ## Пересобрать и пересоздать приложения

down: down-all ## Остановить весь стек, данные сохраняются

# Приложения первыми: пока их контейнеры в сети curier-flow, её не удалить.
down-all: down-apps down-infra ## Остановить приложения, затем инфраструктуру

down-infra: ## Остановить инфраструктуру, volume'ы сохраняются
	$(INFRA) down

down-apps: ## Остановить приложения
	$(APPS) down

delete: delete-all ## Снести весь стек вместе с данными

delete-all: ## Удалить контейнеры, сети и ВСЕ данные
	@printf 'Удалить контейнеры и все данные (postgres, rabbitmq, redis, minio)? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(APPS) down --volumes --remove-orphans
	$(INFRA) down --volumes --remove-orphans

delete-infra: ## Удалить инфраструктуру вместе с данными
	@printf 'Удалить данные postgres, rabbitmq, redis, minio? [y/N] '
	@read answer && [ "$$answer" = "y" ] || { echo "отменено"; exit 1; }
	$(INFRA) down --volumes --remove-orphans

delete-apps: ## Удалить контейнеры приложений и их образы
	$(APPS) down --rmi local --remove-orphans
