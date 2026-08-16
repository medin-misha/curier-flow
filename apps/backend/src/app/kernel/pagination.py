"""Keyset-пагинация: параметры страницы, страница результата и кодек курсора.

OFFSET в шаблоне не используется нигде: на больших таблицах он линейно
деградирует и, что важнее, пропускает и дублирует строки, если между двумя
запросами кто-то вставил или удалил запись. Keyset листает по стабильному
ключу `(created_at, id)`, поэтому вставки в начало списка на уже выданные
страницы не влияют.

`id` входит в ключ не для красоты: `created_at` не уникален, и без второго
компонента строки с одинаковой меткой времени теряются на границе страниц.
"""

import base64
from datetime import datetime
from typing import NamedTuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.kernel.errors import ValidationFailed

#: Разделитель полей внутри курсора. Не встречается ни в ISO-8601, ни в UUID,
#: поэтому разбор однозначен без экранирования.
_SEPARATOR = "|"


class Cursor(NamedTuple):
    """Позиция в списке: последняя выданная клиенту строка."""

    created_at: datetime
    id: UUID


class PageParams(BaseModel):
    """Запрошенная клиентом страница.

    `limit` ограничен сверху, чтобы один запрос не мог вытянуть таблицу
    целиком и занять пул соединений.
    """

    cursor: str | None = None
    limit: int = Field(50, ge=1, le=200)


class Page[T](BaseModel):
    """Страница результата и курсор для следующей.

    `next_cursor is None` означает, что данные кончились.

    `arbitrary_types_allowed` нужен потому, что страницами оперируют оба слоя:
    сервис получает `Page[Widget]` с ORM-сущностями, а API отдаёт наружу
    `Page[WidgetResponse]` со схемами Pydantic.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    next_cursor: str | None


def encode_cursor(created_at: datetime, id_: UUID) -> str:
    """Упаковать позицию в непрозрачную для клиента строку.

    Метка времени сохраняется в ISO-8601 со смещением и микросекундами:
    округление хотя бы до секунд ломает keyset — строки в пределах одной
    секунды начинают пропадать или повторяться.

    Кидает `ValueError`, если `created_at` наивный. Наивная метка не сравнима
    с колонкой `timestamptz`, и такой курсор молча сдвигал бы выборку на
    величину смещения часового пояса.
    """
    if created_at.tzinfo is None:
        raise ValueError("Cursor timestamp must be timezone-aware")
    raw = f"{created_at.isoformat()}{_SEPARATOR}{id_}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Cursor:
    """Разобрать курсор, пришедший от клиента.

    Курсор — часть URL, значит его правят руками, обрезают при копировании и
    подставляют от другой выборки. Любой мусор на входе — ошибка клиента
    (`ValidationFailed`, 422), а не сбой сервера: наружу не должно вылетать ни
    `binascii.Error`, ни `ValueError`.
    """
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
        encoded_at, _, encoded_id = raw.partition(_SEPARATOR)
        created_at = datetime.fromisoformat(encoded_at)
        parsed_id = UUID(encoded_id)
    except ValueError as exc:
        raise ValidationFailed("Malformed pagination cursor", cursor=cursor) from exc
    if created_at.tzinfo is None:
        raise ValidationFailed("Malformed pagination cursor", cursor=cursor)
    return Cursor(created_at=created_at, id=parsed_id)
