.DEFAULT_GOAL := help
.PHONY: help install check test up down migrate revision run worker

# Порты и хост API берутся из окружения, чтобы локальный запуск не конфликтовал
# с другими проектами на машине. Значения по умолчанию совпадают с .env.example.
API_HOST ?= 127.0.0.1
API_PORT ?= 8000

# Порог покрытия ядра. У kernel он свой и жёстче общего: ошибка там расходится
# по всем модулям сразу, а непокрытая ветка в бизнес-модуле стоит одному
# модулю. Общего порога намеренно нет — он превращается в игру с числом.
KERNEL_COVERAGE_MIN ?= 85

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Поставить зависимости (включая dev и test) и git-хуки
	uv sync --all-groups
	uv run pre-commit install

check: ## Формат, линтер, типы, правила зависимостей
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run lint-imports

test: ## Тесты с измерением покрытия; отдельный порог на ядро
	uv run pytest --cov --cov-report=term-missing
	@echo "--- coverage of app.kernel (threshold $(KERNEL_COVERAGE_MIN)%) ---"
	uv run coverage report --include="src/app/kernel/*" --fail-under=$(KERNEL_COVERAGE_MIN)

up: ## Поднять инфраструктуру и дождаться healthy
	docker compose up -d --wait

down: ## Остановить инфраструктуру (данные в volume'ах сохраняются)
	docker compose down

migrate: ## Накатить миграции до последней ревизии
	uv run alembic upgrade head

revision: ## Сгенерировать миграцию: make revision m="add orders"
	@test -n "$(m)" || { echo 'usage: make revision m="описание изменения"'; exit 1; }
	uv run alembic revision --autogenerate -m "$(m)"

run: ## Запустить HTTP-приложение с автоперезагрузкой
	uv run uvicorn app.main:app --reload --host $(API_HOST) --port $(API_PORT)

worker: ## Запустить воркер: TaskIQ, консьюмеры RabbitMQ, релей outbox
	uv run python -m app.worker
