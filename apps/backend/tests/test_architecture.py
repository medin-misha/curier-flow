"""Правила слоёв, проверяемые по исходникам.

Правила модуля («хендлер не ходит в базу», «сервис не знает про HTTP»,
«транзакцией управляет зависимость») не выражаются ни линтером, ни
import-linter: они про то, какой символ появился в каком файле, а не про
пакеты. Пока их сторожит ревью, они держатся ровно до первого спешного
мержа, поэтому здесь они превращены в тесты.

Разбор по AST, а не по grep. Grep находит `session.commit()` в докстринге,
в комментарии «здесь коммитить нельзя» и в строке лога, а первое же ложное
срабатывание учит людей отключать проверку. AST видит только настоящий вызов.

Важное различие, которое обязано пережить любую правку этих тестов: запрещён
`commit()`, а не `begin()`. `src/app/modules/storage/services.py` законно
держит границы транзакций сам (`async with session.begin()`), потому что
каждая его операция сочетает базу и объектное хранилище, а внешний I/O внутри
открытой транзакции недопустим. Правило ловит `commit()` — точку, в которой
атомарная операция распадается на несколько.

У каждой проверки есть страховка от самообмана: тест, который скармливает
детектору заведомо нарушающий файл, и тест, который убеждается, что сканер
вообще что-то нашёл на диске. Без них переезд пакета или опечатка в `rglob`
сделали бы все правила зелёными навсегда.
"""

import ast
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

import app
import app.modules
from app.modules import MODULES

SRC_ROOT = Path(app.__file__).resolve().parent
MODULES_ROOT = Path(app.modules.__file__).resolve().parent

#: Модуль, из которого приезжает CRUD. Хендлеру он запрещён в любом написании.
CRUD_MODULE = "app.kernel.db.crud"

#: Файл, который обязан лежать в каждом бизнес-модуле: инструкции для агента,
#: работающего с этим модулем.
MODULE_INSTRUCTIONS = Path(".claude") / "CLAUDE.md"

#: Зависимость пишущей транзакции. Объявлять её без `scope="function"` нельзя
#: нигде: с областью по умолчанию FastAPI закрывает генератор уже после
#: отправки ответа, и упавший коммит достаётся клиенту как 2xx.
UOW_FACTORY = "get_uow"


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _sources(root: Path, pattern: str) -> list[Path]:
    """Файлы, попадающие под правило, в устойчивом порядке."""
    return sorted(root.rglob(pattern))


def commit_calls(path: Path) -> list[str]:
    """Вызовы `.commit()` в файле: файл, строка и что писать вместо.

    Ищется именно вызов метода `commit`. `begin()` — не он: контекстный
    менеджер транзакции разрешён и модулю, и ядру.
    """
    return [
        f"{path}:{node.lineno} calls .commit()"
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
    ]


def crud_imports(path: Path) -> list[str]:
    """Импорты CRUD в файле — в любом написании, включая импорт модуля."""
    found: list[str] = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            found.extend(
                f"{path}:{node.lineno} imports {alias.name}"
                for alias in node.names
                if alias.name == CRUD_MODULE
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported = {alias.name for alias in node.names}
            if node.module == CRUD_MODULE and "CRUD" in imported:
                found.append(f"{path}:{node.lineno} imports CRUD")
            elif node.module == "app.kernel.db" and "crud" in imported:
                found.append(f"{path}:{node.lineno} imports the crud module")
    return found


def http_exception_uses(path: Path) -> list[str]:
    """Любое упоминание `HTTPException` в файле: импорт, вызов, аннотация."""
    lines: set[int] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Name | ast.Attribute):
            # Голое имя и обращение через модуль (`fastapi.HTTPException`) —
            # одно и то же нарушение, отличается только написание.
            referenced = node.id if isinstance(node, ast.Name) else node.attr
            if referenced == "HTTPException":
                lines.add(node.lineno)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            lines.update(
                node.lineno for alias in node.names if alias.name.endswith("HTTPException")
            )
    return [f"{path}:{line} mentions HTTPException" for line in sorted(lines)]


def unscoped_uow_dependencies(path: Path) -> list[str]:
    """Объявления `Depends(get_uow)` без `scope="function"`.

    Псевдоним пишущей транзакции неизбежно дублируется: правило слоёв
    запрещает бизнес-модулю импортировать `app.api.deps`, поэтому каждый
    модуль объявляет свой. Вместе со строкой дублируется и способ ошибиться —
    забыть область и вернуть клиенту 2xx на несостоявшийся коммит.

    Проверяется имя, а не объект: до вызова `Depends` здесь дело не доходит,
    зато написание `Depends(get_uow, ...)` и `Depends(session.get_uow, ...)`
    одинаково видны в дереве.
    """
    found: list[str] = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Call) or _called_name(node.func) != "Depends":
            continue
        if not node.args or _called_name(node.args[0]) != UOW_FACTORY:
            continue
        if not any(
            keyword.arg == "scope"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "function"
            for keyword in node.keywords
        ):
            found.append(f"{path}:{node.lineno} declares Depends({UOW_FACTORY}) without scope")
    return found


def _called_name(node: ast.expr) -> str | None:
    """Последний компонент имени: `get_uow` и `session.get_uow` — одно и то же."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def module_packages(root: Path) -> set[str]:
    """Имена пакетов верхнего уровня в каталоге модулей."""
    return {
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "__init__.py").is_file()
    }


def _scan(paths: Iterable[Path], rule: Callable[[Path], list[str]]) -> list[str]:
    """Применить детектор ко всем файлам и собрать находки."""
    offenders: list[str] = []
    for path in paths:
        offenders.extend(rule(path))
    return offenders


def test_modules_never_commit_the_session() -> None:
    """Границу транзакции ставит владелец запроса, а не бизнес-код."""
    offenders = _scan(_sources(MODULES_ROOT, "*.py"), commit_calls)

    assert not offenders, (
        "business modules must not commit: " + "; ".join(offenders) + ". Let the get_uow "
        "dependency own the transaction, or wrap the write in `async with session.begin()` "
        "when the module owns the boundary itself. A bare commit() splits one atomic "
        "operation into several and makes rollback stop rolling back."
    )


def test_handlers_never_import_crud() -> None:
    """Хендлер занимается HTTP; в базу за него ходит сервис."""
    offenders = _scan(_sources(SRC_ROOT, "handlers.py"), crud_imports)

    assert not offenders, (
        "handlers must not reach into persistence: " + "; ".join(offenders) + ". Move the "
        "CRUD call into services.py of the same module and let the handler call the service."
    )


def test_services_never_raise_http_exceptions() -> None:
    """Сервис не знает, что его вызвали по HTTP."""
    offenders = _scan(_sources(SRC_ROOT, "services.py"), http_exception_uses)

    assert not offenders, (
        "services must stay transport-agnostic: " + "; ".join(offenders) + ". Raise an "
        "AppError subclass from app.kernel.errors (NotFound, Conflict, ValidationFailed, "
        "...) instead: app.api.errors turns it into an RFC 9457 problem+json response, and "
        "the same service stays usable from a worker or a script."
    )


def test_uow_dependencies_close_before_the_response() -> None:
    """Пишущая транзакция закрывается до отправки ответа — в любом файле."""
    offenders = _scan(_sources(SRC_ROOT, "*.py"), unscoped_uow_dependencies)

    assert not offenders, (
        "write transactions must close before the response is sent: "
        + "; ".join(offenders)
        + '. Declare the alias as Annotated[AsyncSession, Depends(get_uow, scope="function")]. '
        "With the default request scope FastAPI closes the dependency after the response has "
        "been sent, so a failing COMMIT reaches the client as 2xx and the exception only "
        "reaches the log."
    )


def test_every_module_package_is_registered() -> None:
    """Пакет, которого нет в `MODULES`, не входит в приложение."""
    missing = sorted(module_packages(MODULES_ROOT) - {module.name for module in MODULES})

    assert not missing, (
        f"packages under src/app/modules are absent from MODULES: {', '.join(missing)}. "
        f"Add their Module manifest to src/app/modules/__init__.py: the registry is the only "
        f"source of routes, models, subscribers, tasks and broker topology."
    )


def test_every_module_carries_agent_instructions() -> None:
    """Модуль без своего CLAUDE.md — модуль, который агент будет писать наугад."""
    missing = sorted(
        name
        for name in module_packages(MODULES_ROOT)
        if not (MODULES_ROOT / name / MODULE_INSTRUCTIONS).is_file()
    )

    assert not missing, (
        f"modules without {MODULE_INSTRUCTIONS}: {', '.join(missing)}. Every module documents "
        f"its own rules next to its code: create "
        f"src/app/modules/<name>/{MODULE_INSTRUCTIONS}."
    )


def write(path: Path, source: str) -> Path:
    """Положить исходник на диск: детекторы читают файлы, а не строки."""
    path.write_text(source, encoding="utf-8")
    return path


def test_commit_detector_sees_a_real_violation(tmp_path: Path) -> None:
    """Страховка: детектор обязан находить настоящий вызов."""
    offender = write(
        tmp_path / "services.py",
        "async def save(session):\n"
        '    """Коммитить тут нельзя: session.commit() ломает атомарность."""\n'
        "    # session.commit()\n"
        "    await session.commit()\n",
    )

    assert commit_calls(offender) == [f"{offender}:4 calls .commit()"]


def test_commit_detector_allows_an_explicit_transaction(tmp_path: Path) -> None:
    """Страховка от противоположной ошибки: `begin()` — законный способ."""
    allowed = write(
        tmp_path / "services.py",
        "async def save(session_factory):\n"
        "    async with session_factory() as session, session.begin():\n"
        "        session.add(object())\n",
    )

    assert commit_calls(allowed) == []


def test_crud_detector_sees_every_spelling(tmp_path: Path) -> None:
    offender = write(
        tmp_path / "handlers.py",
        "from app.kernel.db.crud import CRUD\n"
        "from app.kernel.db import crud\n"
        "import app.kernel.db.crud\n",
    )

    assert len(crud_imports(offender)) == 3


def test_crud_detector_ignores_a_mention_in_prose(tmp_path: Path) -> None:
    innocent = write(
        tmp_path / "handlers.py",
        '"""Хендлер не импортирует CRUD: from app.kernel.db.crud import CRUD."""\n',
    )

    assert crud_imports(innocent) == []


def test_http_exception_detector_sees_import_and_raise(tmp_path: Path) -> None:
    offender = write(
        tmp_path / "services.py",
        "import fastapi\n"
        "from fastapi import HTTPException\n"
        "\n"
        "def fail():\n"
        "    raise HTTPException(status_code=404)\n"
        "\n"
        "def fail_qualified():\n"
        "    raise fastapi.HTTPException(status_code=404)\n",
    )

    assert len(http_exception_uses(offender)) == 3


def test_http_exception_detector_ignores_a_mention_in_prose(tmp_path: Path) -> None:
    innocent = write(
        tmp_path / "services.py",
        '"""Сервис не кидает HTTPException: это дело слоя api."""\n',
    )

    assert http_exception_uses(innocent) == []


def test_uow_detector_sees_a_missing_scope(tmp_path: Path) -> None:
    """Страховка: детектор обязан находить забытую область."""
    offender = write(
        tmp_path / "handlers.py",
        "from fastapi import Depends\n"
        "from app.kernel.db.session import get_uow\n"
        "\n"
        "Uow = Annotated[AsyncSession, Depends(get_uow)]\n",
    )

    assert unscoped_uow_dependencies(offender) == [
        f"{offender}:4 declares Depends(get_uow) without scope"
    ]


def test_uow_detector_accepts_the_correct_declaration(tmp_path: Path) -> None:
    """Страховка от противоположной ошибки: правильное объявление проходит."""
    allowed = write(
        tmp_path / "handlers.py",
        "from app.kernel.db import session\n"
        "\n"
        'Uow = Annotated[AsyncSession, Depends(session.get_uow, scope="function")]\n'
        "RoSession = Annotated[AsyncSession, Depends(session.get_ro_session)]\n",
    )

    assert unscoped_uow_dependencies(allowed) == []


def test_package_scan_ignores_directories_without_init(tmp_path: Path) -> None:
    (tmp_path / "orders").mkdir()
    (tmp_path / "orders" / "__init__.py").touch()
    (tmp_path / "__pycache__").mkdir()

    assert module_packages(tmp_path) == {"orders"}


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [("handlers.py", 2), ("services.py", 2)],
)
def test_scan_actually_sees_layer_files(pattern: str, expected: int) -> None:
    """Страховка: правила выше проверяют настоящие файлы, а не пустой список."""
    found = _sources(SRC_ROOT, pattern)

    assert len(found) >= expected
    assert {path.parent.name for path in found} >= {"health", "storage"}


def test_scan_actually_sees_module_sources() -> None:
    """Страховка: обход каталога модулей находит их исходники и пакеты."""
    scanned = {path.name for path in _sources(MODULES_ROOT, "*.py")}

    assert {"handlers.py", "services.py", "module.py"} <= scanned
    assert module_packages(MODULES_ROOT) >= {"health", "storage"}
