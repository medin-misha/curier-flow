"""Ядро не должно знать ни о веб-фреймворке, ни о слоях над собой.

Правило «kernel не импортирует fastapi» словами не проверяется: import-linter
следит за слоями внутри `app`, но fastapi ему внешний пакет. Один случайный
`from fastapi import Depends` в `kernel/db/session.py` — и ядро больше нельзя
использовать в воркере и в миграциях. Поэтому проверка исходников.

Запрещён именно рантайм-импорт. Манифест модуля обязан ссылаться на `APIRouter`
и `FastAPI` в аннотациях, иначе реестр невозможно описать типами, поэтому в
`registry.py` такие импорты разрешены под `if TYPE_CHECKING:` — они не
выполняются и зависимости не создают. Остальным файлам ядра не нужно и это.

Верхние слои `app` проверяются здесь же, хотя за ними следит и import-linter:
пока `app.platform` пуст, нарушать там нечего, и правило легко проглядеть при
ревью. Проверка по исходникам сработает в тот же день, когда в `platform`
появится первый модуль и кто-нибудь позовёт его из `kernel/events`.
"""

import ast
from pathlib import Path

import app.kernel

KERNEL_ROOT = Path(app.kernel.__file__).resolve().parent

#: Starlette проверяется вместе с fastapi: это его внутренности, и импорт
#: оттуда протаскивает в ядро ту же зависимость от HTTP-транспорта.
FORBIDDEN_ROOTS = ("fastapi", "starlette")

#: Слои, лежащие над ядром. Ядро обязано собираться без единого из них:
#: на него опираются и воркер, и миграции, и тесты самого ядра.
FORBIDDEN_LAYERS = ("app.api", "app.modules", "app.platform")

#: Единственный файл ядра, которому разрешены аннотационные импорты фреймворка.
TYPE_ONLY_EXCEPTION = "registry.py"


def _is_type_checking(node: ast.expr) -> bool:
    """`TYPE_CHECKING` или `typing.TYPE_CHECKING` в условии `if`."""
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"


def _type_checking_imports(tree: ast.AST) -> set[ast.stmt]:
    guarded: set[ast.stmt] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not _is_type_checking(node.test):
            continue
        for statement in node.body:
            guarded.update(
                child
                for child in ast.walk(statement)
                if isinstance(child, ast.Import | ast.ImportFrom)
            )
    return guarded


def _imported_modules(tree: ast.AST, *, type_checking: bool) -> list[tuple[int, str]]:
    guarded = _type_checking_imports(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (node in guarded) is not type_checking:
            continue
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module))
    return found


def _forbidden(path: Path, *, type_checking: bool) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path}:{lineno} imports {module}"
        for lineno, module in _imported_modules(tree, type_checking=type_checking)
        if module.split(".", 1)[0] in FORBIDDEN_ROOTS
    ]


def _upper_layers(path: Path) -> list[str]:
    """Импорты вышележащих слоёв в файле — и рантайм, и аннотационные."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = _imported_modules(tree, type_checking=False) + _imported_modules(
        tree, type_checking=True
    )
    return [
        f"{path}:{lineno} imports {module}"
        for lineno, module in imports
        for layer in FORBIDDEN_LAYERS
        if module == layer or module.startswith(f"{layer}.")
    ]


def test_kernel_does_not_import_web_framework() -> None:
    offenders: list[str] = []
    for path in sorted(KERNEL_ROOT.rglob("*.py")):
        offenders.extend(_forbidden(path, type_checking=False))

    assert not offenders, "kernel must not depend on the web framework: " + "; ".join(offenders)


def test_only_registry_annotates_framework_types() -> None:
    offenders: list[str] = []
    for path in sorted(KERNEL_ROOT.rglob("*.py")):
        if path.name == TYPE_ONLY_EXCEPTION:
            continue
        offenders.extend(_forbidden(path, type_checking=True))

    assert not offenders, (
        "only kernel/registry.py may reference framework types under TYPE_CHECKING: "
        + "; ".join(offenders)
    )


def test_registry_keeps_framework_types_behind_type_checking() -> None:
    """Страховка: исключение из правила должно оставаться настоящим исключением."""
    registry = KERNEL_ROOT / TYPE_ONLY_EXCEPTION

    assert _forbidden(registry, type_checking=True)
    assert not _forbidden(registry, type_checking=False)


def test_kernel_does_not_import_upper_layers() -> None:
    """Публикацией событий занимается релей из `platform`, а не ядро."""
    offenders: list[str] = []
    for path in sorted(KERNEL_ROOT.rglob("*.py")):
        offenders.extend(_upper_layers(path))

    assert not offenders, "kernel must not depend on api, modules or platform: " + "; ".join(
        offenders
    )


def test_upper_layer_scan_catches_a_violation(tmp_path: Path) -> None:
    """Страховка: пока `app.platform` пуст, нарушать в нём нечего."""
    offender = tmp_path / "leaky.py"
    offender.write_text(
        "from typing import TYPE_CHECKING\n\n"
        "from app.platform.rabbitmq import publish\n\n"
        "if TYPE_CHECKING:\n"
        "    from app.modules.orders.models import Order\n",
        encoding="utf-8",
    )

    assert len(_upper_layers(offender)) == 2


def test_scan_actually_sees_kernel_sources() -> None:
    """Страховка от проверки, которая ничего не проверяет.

    Если пакет переедет или `rglob` перестанет что-то находить, тесты выше
    станут зелёными навсегда.
    """
    scanned = {path.name for path in KERNEL_ROOT.rglob("*.py")}
    assert {"config.py", "context.py", "errors.py", "pagination.py", "registry.py"} <= scanned
    assert {"bus.py", "models.py"} <= scanned
