"""Проверка целостности раскладки проекта.

Раскладка — часть контракта шаблона: на неё завязаны правила import-linter,
per-file-ignores ruff и строгие секции mypy. Если пакет переименовали или
потеряли, все эти проверки молча перестают что-либо проверять, поэтому
существование пакетов проверяется тестом.
"""

import importlib
import platform
from pathlib import Path

import pytest

import app

#: Пакеты, на которых держатся правила зависимостей api -> modules -> platform -> kernel.
PACKAGES = (
    "app",
    "app.api",
    "app.kernel",
    "app.kernel.db",
    "app.kernel.events",
    "app.kernel.security",
    "app.platform",
    "app.modules",
)

SRC_ROOT = Path(app.__file__).resolve().parent


@pytest.mark.parametrize("name", PACKAGES)
def test_package_is_importable(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__file__ is not None, f"{name} is a namespace package, expected a real one"
    assert Path(module.__file__).name == "__init__.py", f"{name} must be a package, not a module"


@pytest.mark.parametrize("name", PACKAGES)
def test_package_lives_under_src_app(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__file__ is not None
    assert Path(module.__file__).resolve().is_relative_to(SRC_ROOT)


def test_stdlib_platform_is_not_shadowed() -> None:
    """`app.platform` не должен перехватывать импорт одноимённого модуля stdlib."""
    assert platform.__file__ is not None
    assert not Path(platform.__file__).resolve().is_relative_to(SRC_ROOT)
    assert platform.python_version_tuple()[0] == "3"
