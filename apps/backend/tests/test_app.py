"""Сборка приложения: пустой реестр, документация, монтирование роутеров."""

import pytest
from fastapi import APIRouter, FastAPI

from app.api.router import build_router
from app.kernel.config import settings
from app.kernel.registry import Module
from app.main import app as module_app
from tests.asgi import app_client


def widgets_module(prefix: str | None = None) -> Module:
    router = APIRouter()

    @router.get("/")
    async def list_widgets() -> list[str]:
        return ["bolt"]

    return Module(name="widgets", router=router, prefix=prefix)


def test_module_app_is_built_from_the_registry() -> None:
    assert isinstance(module_app, FastAPI)
    assert module_app.title == settings.app_name
    assert module_app.version == settings.app_version


async def test_empty_registry_produces_a_working_app() -> None:
    async with app_client() as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["paths"] == {}


async def test_docs_are_open_with_default_settings() -> None:
    async with app_client() as client:
        response = await client.get("/docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_are_closed_outside_debug(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "debug", False)

    async with app_client() as client:
        response = await client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_module_router_is_mounted_under_its_name() -> None:
    async with app_client([widgets_module()]) as client:
        response = await client.get("/widgets/")

    assert response.status_code == 200
    assert response.json() == ["bolt"]


async def test_explicit_prefix_is_used_as_is() -> None:
    async with app_client([widgets_module(prefix="/v1/widgets")]) as client:
        response = await client.get("/v1/widgets/")

    assert response.status_code == 200


def test_modules_without_router_are_skipped() -> None:
    """Модуль без HTTP-поверхности — норма: подписчик или набор задач."""
    assert build_router([Module(name="relay")]).routes == []
    assert len(build_router([Module(name="relay"), widgets_module()]).routes) == 1
