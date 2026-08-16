"""Сборка главного роутера приложения из реестра модулей."""

from collections.abc import Sequence

from fastapi import APIRouter

from app.kernel.registry import Module


def build_router(modules: Sequence[Module]) -> APIRouter:
    """Собрать главный роутер: по одному include_router на модуль с HTTP.

    Модули без роутера пропускаются молча: у подписчика событий или у набора
    задач TaskIQ HTTP-поверхности нет, и это норма, а не ошибка конфигурации.
    """
    router = APIRouter()
    for module in modules:
        if module.router is None:
            continue
        router.include_router(module.router, prefix=module.url_prefix)
    return router
