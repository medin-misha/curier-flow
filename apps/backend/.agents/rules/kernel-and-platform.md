> Область применения: `src/app/kernel/**/*.py`,
> `src/app/platform/**/*.py`.

# Ядро и платформа: усиленные требования

Общий стиль кода задан настройками `ruff` и `mypy` в `pyproject.toml`. Сверх
них в `kernel` и `platform` действует следующее — потому что это код, который
читают и переиспользуют все модули, и ошибка в нём тиражируется:

- **докстринг обязателен** у публичного модуля, класса и функции: что делает,
  что принимает, что возвращает, чем кидается. В `api`, `modules` и точках
  входа требование снято;
- `mypy` здесь строже, чем в остальном проекте: дополнительно включены
  `disallow_any_generics`, `disallow_subclassing_any`, `disallow_untyped_calls`,
  `disallow_untyped_decorators`;
- покрытие `app.kernel` не опускается ниже 85% — отдельный порог в `make test`.

**Проверяют:** `make check` (`ruff check` с правилом `D`, `mypy` с секциями для
`app.kernel` и `app.platform` из `pyproject.toml`), `make test` (порог покрытия).
