"""Метка ручки, которой нужен access-токен администратора.

Ядро не знает про FastAPI: декоратор только ставит признак на функцию. После
сборки приложения слой ``api`` находит отмеченные endpoints и подключает
транспортную проверку Bearer JWT. Такой же приём используется для
идемпотентности, подписчиков событий и периодических задач.
"""

from collections.abc import Callable
from typing import Any, Final

#: Атрибут функции, который читает сборка HTTP-приложения.
AUTHENTICATED_ATTR: Final = "__authenticated__"


def authenticated[Handler: Callable[..., Any]](handler: Handler) -> Handler:
    """Пометить endpoint как требующий access JWT администратора.

    Принимает функцию-обработчик и возвращает её без обёртки. Кидает
    ``TypeError`` только если вызывающий передал объект, которому нельзя
    установить атрибут; обычные функции всегда поддерживаются.
    """
    setattr(handler, AUTHENTICATED_ATTR, True)
    return handler


def is_authenticated(handler: Callable[..., Any]) -> bool:
    """Проверить наличие метки обязательной аутентификации на endpoint."""
    return bool(getattr(handler, AUTHENTICATED_ATTR, False))
