"""Реестр модулей: полнота списка, сборка lifespan, пакеты моделей."""

import dataclasses
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI

import app.modules
from app.kernel.registry import (
    ConsumerDecl,
    Module,
    TopologyDecl,
    build_lifespan,
    iter_model_packages,
)
from app.modules import MODULES

MODULES_ROOT = Path(app.modules.__file__).resolve().parent

ModuleLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def module_dirs(root: Path) -> set[str]:
    """Имена директорий, которые выглядят как бизнес-модуль."""
    return {manifest.parent.name for manifest in root.glob("*/module.py")}


def test_every_module_on_disk_is_registered() -> None:
    missing = sorted(module_dirs(MODULES_ROOT) - {module.name for module in MODULES})

    assert not missing, (
        f"Modules found on disk but missing from MODULES: {', '.join(missing)}. "
        f"Add their Module manifest to src/app/modules/__init__.py: the registry is the "
        f"only source of routes, models, subscribers, tasks and broker topology, so a "
        f"module absent from it is absent from the application."
    )


def test_every_registered_module_exists_on_disk() -> None:
    """Обратная проверка: опечатка в имени не должна проходить молча."""
    stale = sorted({module.name for module in MODULES} - module_dirs(MODULES_ROOT))

    assert not stale, (
        f"MODULES lists modules without src/app/modules/<name>/module.py: {', '.join(stale)}. "
        f"Module.name must match the package directory name."
    )


def test_scan_finds_a_module_directory(tmp_path: Path) -> None:
    """Страховка от проверки, которая ничего не проверяет.

    Если `glob` перестанет находить манифесты, оба теста выше станут зелёными
    навсегда, а реестр — необязательным.
    """
    (tmp_path / "orders").mkdir()
    (tmp_path / "orders" / "module.py").touch()
    (tmp_path / "not_a_module").mkdir()

    assert module_dirs(tmp_path) == {"orders"}


def test_default_prefix_is_module_name() -> None:
    assert Module(name="orders").url_prefix == "/orders"


def test_explicit_prefix_wins() -> None:
    assert Module(name="orders", prefix="/v1/orders").url_prefix == "/v1/orders"
    assert Module(name="root", prefix="").url_prefix == ""


def test_manifest_is_immutable() -> None:
    module = Module(name="orders")

    with pytest.raises(dataclasses.FrozenInstanceError):
        module.name = "other"  # type: ignore[misc]


def test_declarations_carry_defaults() -> None:
    async def handler() -> None: ...

    topology = TopologyDecl(exchange="orders", queue="orders.sync", routing_key="order.*")
    consumer = ConsumerDecl(queue="orders.sync", handler=handler)

    assert (topology.exchange_type, topology.durable, topology.dead_letter) == ("topic", True, True)
    assert topology.retry_ttl_ms is None
    assert dict(topology.arguments) == {}
    assert (consumer.prefetch, consumer.requires_idempotency) == (16, True)


def test_model_packages_keep_order_and_drop_duplicates() -> None:
    modules = (
        Module(name="orders", models="app.modules.orders.models"),
        Module(name="health"),
        Module(name="billing", models="app.modules.orders.models"),
        Module(name="storage", models="app.modules.storage.models"),
    )

    assert list(iter_model_packages(modules)) == [
        "app.modules.orders.models",
        "app.modules.storage.models",
    ]


def test_registry_is_a_tuple_of_modules() -> None:
    assert isinstance(MODULES, tuple)
    assert all(isinstance(module, Module) for module in MODULES)


async def test_lifespan_enters_and_exits_in_order() -> None:
    events: list[str] = []

    def make_lifespan(name: str) -> ModuleLifespan:
        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            events.append(f"start:{name}")
            yield
            events.append(f"stop:{name}")

        return lifespan

    modules = (
        Module(name="first", lifespan=make_lifespan("first")),
        Module(name="second", router=APIRouter()),
        Module(name="third", lifespan=make_lifespan("third")),
    )

    async with build_lifespan(modules)(FastAPI()):
        assert events == ["start:first", "start:third"]

    assert events == ["start:first", "start:third", "stop:third", "stop:first"]


async def test_lifespan_unwinds_started_modules_on_failure() -> None:
    """Упавшая инициализация обязана закрыть то, что уже поднялось."""
    events: list[str] = []

    @asynccontextmanager
    async def healthy(_app: FastAPI) -> AsyncIterator[None]:
        events.append("start")
        # finally, а не код после yield: при падении соседнего модуля
        # исключение прилетает в точку yield и до следующей строки не доходит.
        try:
            yield
        finally:
            events.append("stop")

    @asynccontextmanager
    async def broken(_app: FastAPI) -> AsyncIterator[None]:
        raise RuntimeError("broker is down")
        yield

    modules = (
        Module(name="healthy", lifespan=healthy),
        Module(name="broken", lifespan=broken),
    )

    with pytest.raises(RuntimeError, match="broker is down"):
        async with build_lifespan(modules)(FastAPI()):
            pass

    assert events == ["start", "stop"]


async def test_empty_registry_has_a_usable_lifespan() -> None:
    async with build_lifespan(())(FastAPI()):
        pass
