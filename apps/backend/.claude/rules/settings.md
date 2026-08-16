---
paths:
  - "src/app/**/config.py"
  - "src/app/modules/**/*.py"
  - "src/app/platform/**/*.py"
  - ".env.example"
---

# Настройки

- окружение читается **только** через pydantic-settings. `os.getenv` и
  `os.environ` запрещены линтером;
- общие настройки — в `kernel/config.py`; настройки подсистемы объявляются
  рядом с её владельцем (`StorageSettings` в `modules/storage/services.py`,
  `S3Settings` в `platform/s3.py`);
- у класса настроек модуля `env_prefix="<name>_"`, `extra="ignore"`;
- каждая новая переменная попадает в `.env.example` с объяснением, зачем она и
  чем грозит неудачное значение;
- дефолты в коде совпадают с `.env.example`: шаблон обязан запускаться сразу
  после `git clone`.

**Проверяют:** `make check` (ruff `banned-api` на `os.getenv`/`os.environ`),
`tests/test_config.py`, `tests/test_platform_settings.py`,
`tests/test_worker.py::test_defaults_match_the_env_example`.

Полнота `.env.example` для **новых** настроек **проверяется ревью**: сверка
«каждое поле каждого Settings-класса упомянуто в файле» существует только для
тех классов, у которых она написана поимённо. Скилл создания модуля требует
дописать переменные модуля в `.env.example`.
