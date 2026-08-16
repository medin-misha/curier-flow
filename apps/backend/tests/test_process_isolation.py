"""HTTP-процесс не поднимает фоновую работу и не ходит в брокер.

Правило шаблона: консьюмеры, шедулер и релей живут только в `app.worker`.
Буквальный запрет импортировать `app.platform` из процесса uvicorn невозможен —
проверка готовности обязана дотянуться до брокера и хранилища, а живёт она в
обычном модуле, который собирается в приложение. Проверяемая суть правила
другая: точка входа и слой api не знают про платформу в принципе, а полный
прогон lifespan не открывает ни одного соединения.
"""

import ast
import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import app
from tests.asgi import app_client

SRC_ROOT = Path(app.__file__).resolve().parent

#: Файлы, исполняемые процессом uvicorn и только им.
HTTP_PROCESS_FILES = (SRC_ROOT / "main.py", *sorted((SRC_ROOT / "api").rglob("*.py")))


def platform_imports(path: Path) -> list[str]:
    """Импорты `app.platform` в файле — и рантайм, и аннотационные.

    `TYPE_CHECKING` здесь не оправдание: аннотация типом из платформы означает,
    что HTTP-слой знает о брокере, и рано или поздно кто-то уберёт кавычки.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(
                f"{path}:{node.lineno} imports {alias.name}"
                for alias in node.names
                if _is_platform(alias.name)
            )
        elif isinstance(node, ast.ImportFrom) and node.module and _is_platform(node.module):
            found.append(f"{path}:{node.lineno} imports {node.module}")
    return found


def _is_platform(module: str) -> bool:
    return module == "app.platform" or module.startswith("app.platform.")


def test_http_entrypoint_does_not_import_platform() -> None:
    offenders = [offender for path in HTTP_PROCESS_FILES for offender in platform_imports(path)]

    assert not offenders, (
        "main.py and app.api must not import app.platform: brokers, schedulers and object "
        "storage belong to app.worker. " + "; ".join(offenders)
    )


def test_scan_sees_the_http_process_sources() -> None:
    """Страховка от проверки, которая ничего не проверяет."""
    scanned = {path.name for path in HTTP_PROCESS_FILES}

    assert {"main.py", "router.py", "errors.py", "middleware.py", "deps.py"} <= scanned


def test_scan_catches_a_violation(tmp_path: Path) -> None:
    offender = tmp_path / "leaky.py"
    offender.write_text(
        "from typing import TYPE_CHECKING\n\n"
        "import app.platform.taskiq\n\n"
        "if TYPE_CHECKING:\n"
        "    from app.platform.s3 import ObjectStorage\n",
        encoding="utf-8",
    )

    assert len(platform_imports(offender)) == 2


async def test_lifespan_opens_no_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """Полный прогон lifespan с пустым реестром не создаёт ни одного соединения.

    Запрещается сам транспорт, а не конкретный адрес: и asyncpg, и aiormq, и
    redis идут в сеть через `loop.create_connection`, поэтому подмена ловит
    любую попытку — включая ту, которую добавят завтра.
    """
    attempts: list[str] = []

    async def refuse(
        _self: asyncio.AbstractEventLoop,
        _protocol_factory: Callable[[], asyncio.BaseProtocol],
        host: str | None = None,
        port: int | None = None,
        **_kwargs: Any,
    ) -> None:
        attempts.append(f"{host}:{port}")
        raise AssertionError(f"the HTTP process opened a connection to {host}:{port}")

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "create_connection", refuse)

    async with app_client(lifespan=True) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert attempts == []
