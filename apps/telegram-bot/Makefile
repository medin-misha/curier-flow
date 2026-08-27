.DEFAULT_GOAL := help
.PHONY: help install check test run

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Установить runtime, dev и test зависимости из lockfile
	uv sync --locked --all-groups

check: ## Проверить context, lockfile, формат, lint и типы
	../../scripts/check-agent-context.sh
	uv lock --check
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy

test: ## Запустить unit и stub-integration тесты с покрытием
	uv run pytest --cov=telegram_bot --cov-report=term-missing

run: ## Запустить sending-only worker локально
	uv run python -m telegram_bot.worker
