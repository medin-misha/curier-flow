.DEFAULT_GOAL := help
.PHONY: help install check test test-all revision

# Секции определяются каталогами: новый модуль не требует правки Makefile.
TEST_SCOPES := $(sort $(patsubst tests/%/,%,$(dir $(wildcard tests/*/test_*.py))))
PYTEST_ARGS ?=

# Порог покрытия ядра. У kernel он свой и жёстче общего: ошибка там расходится
# по всем модулям сразу, а непокрытая ветка в бизнес-модуле стоит одному
# модулю. Общего порога намеренно нет — он превращается в игру с числом.
KERNEL_COVERAGE_MIN ?= 85

help: ## Показать список целей
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-10s\033[0m %s\n", $$1, $$2}'
	@printf '\nСекции тестов: $(TEST_SCOPES)\nДля одной секции: make test-courier\n'

install: ## Поставить зависимости (включая dev и test) и git-хуки
	uv sync --all-groups
	uv run pre-commit install

check: ## Формат, линтер, типы, правила зависимостей
	../../scripts/check-agent-context.sh
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run lint-imports

test: ## Только выбранные секции: make test scope="courier transport"
	@test -n "$(strip $(scope))" || { \
		echo 'Укажи scope: $(TEST_SCOPES). Полный прогон: make test-all.'; exit 2; }
	@test -z "$(filter-out $(TEST_SCOPES),$(scope))" || { \
		echo 'Неизвестные секции: $(filter-out $(TEST_SCOPES),$(scope))'; exit 2; }
	uv run pytest $(addprefix tests/,$(sort $(scope))) $(PYTEST_ARGS)

.PHONY: $(addprefix test-,$(TEST_SCOPES))
$(addprefix test-,$(TEST_SCOPES)): test-%:
	$(MAKE) test scope="$*"

test-all: ## Полный прогон с покрытием; только по явному запросу
	uv run pytest tests --cov --cov-report=term-missing $(PYTEST_ARGS)
	@echo "--- coverage of app.kernel (threshold $(KERNEL_COVERAGE_MIN)%) ---"
	uv run coverage report --include="src/app/kernel/*" --fail-under=$(KERNEL_COVERAGE_MIN)

revision: ## Сгенерировать миграцию: make revision m="add orders"
	@test -n "$(m)" || { echo 'usage: make revision m="описание изменения"'; exit 1; }
	uv run alembic revision --autogenerate -m "$(m)"
