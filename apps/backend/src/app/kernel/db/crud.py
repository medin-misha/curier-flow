"""Типовые операции над одной таблицей.

Набор намеренно узкий: create/get/update/delete/страница. Всё, что сложнее —
джойны, агрегаты, батчи — пишется запросом в сервисе. Обобщённый «репозиторий
на все случаи» здесь не заводится: он всегда оказывается либо дырявым, либо
переписанным SQL на Python.

Вызывать `CRUD` вправе только `services.py`. Хендлер, дошедший до CRUD в
обход сервиса, обходит вместе с ним и все бизнес-правила.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.base import Base
from app.kernel.errors import Conflict, NotFound
from app.kernel.pagination import Page, PageParams, decode_cursor, encode_cursor

T = TypeVar("T", bound=Base)


class _KeysetRow(Protocol):
    """Строка, пригодная для keyset-пагинации.

    Нужен только чтобы прочитать ключ у объекта, статический тип которого —
    произвольный наследник `Base`. Наличие колонок проверяется по мапперу
    до запроса, поэтому приведение к этому протоколу безопасно.
    """

    created_at: datetime
    id: UUID


class CRUD:
    """Операции над моделью. Без состояния: сессия передаётся аргументом."""

    @staticmethod
    async def create(model: type[T], dto: BaseModel, session: AsyncSession, **overrides: Any) -> T:
        """Создать строку из схемы запроса.

        Значения `overrides` перекрывают одноимённые поля схемы: всё, что
        определяет сервер (владелец из токена, начальный статус), задаётся
        именно так, а не полем в схеме, — иначе клиент сможет это подменить.

        Делает `flush()`, чтобы сгенерированные БД значения (`created_at`)
        и `id` были доступны сразу, до коммита.
        """
        values = dto.model_dump()
        values.update(overrides)
        obj = model(**values)
        session.add(obj)
        await session.flush()
        return obj

    @staticmethod
    async def get(model: type[T], pk: Any, session: AsyncSession) -> T | None:
        """Вернуть строку по первичному ключу или None, если её нет."""
        return await session.get(model, pk)

    @staticmethod
    async def get_or_404(model: type[T], pk: Any, session: AsyncSession) -> T:
        """Вернуть строку по первичному ключу либо поднять `NotFound`.

        Отдельный метод, чтобы «нет строки → 404» не расползалось по сервисам
        в виде десятка одинаковых `if obj is None`.
        """
        obj = await session.get(model, pk)
        if obj is None:
            raise NotFound(f"{model.__name__} not found", resource=model.__name__, pk=str(pk))
        return obj

    @staticmethod
    async def update(
        obj: T,
        patch: BaseModel,
        session: AsyncSession,
        *,
        allowed: frozenset[str] | None = None,
    ) -> T:
        """Применить частичное обновление, проверив белый список полей.

        Учитываются только явно переданные клиентом поля (`exclude_unset`):
        иначе PATCH затирал бы всё, чего в запросе не было, дефолтами схемы.

        Поле вне белого списка — ошибка (`Conflict`), а не тихая фильтрация:
        клиент, попросивший сменить `status`, должен узнать, что этого не
        произошло, а не считать запрос выполненным.
        """
        changes = patch.model_dump(exclude_unset=True)
        whitelist = type(obj).__patchable__ if allowed is None else allowed
        forbidden = sorted(set(changes) - whitelist)
        if forbidden:
            raise Conflict(
                f"Fields are not patchable: {', '.join(forbidden)}",
                fields=forbidden,
            )
        for name, value in changes.items():
            setattr(obj, name, value)
        await session.flush()
        return obj

    @staticmethod
    async def delete(obj: T, session: AsyncSession) -> None:
        """Удалить строку физически.

        Мягкое удаление — это обновление `deleted_at`, и делает его сервис:
        решение «строку можно потерять» слишком важное, чтобы прятать его за
        флагом общего метода.
        """
        await session.delete(obj)
        await session.flush()

    @staticmethod
    async def list_page(
        model: type[T],
        session: AsyncSession,
        *,
        page: PageParams,
        where: Sequence[Any] = (),
    ) -> Page[T]:
        """Вернуть страницу по keyset-курсору `(created_at, id)`.

        Запрашивается на одну строку больше, чем нужно: её наличие — признак
        того, что за страницей есть данные. Отдельный COUNT для этого не
        делается, он стоит полного прохода по таблице.
        """
        columns = model.__mapper__.columns
        missing = [name for name in ("created_at", "id") if name not in columns]
        if missing:
            raise TypeError(
                f"{model.__name__} has no {', '.join(missing)}: "
                f"keyset pagination requires both created_at and id columns"
            )

        created_at = columns["created_at"]
        identifier = columns["id"]
        stmt = (
            select(model)
            .where(*where)
            .order_by(created_at.desc(), identifier.desc())
            .limit(page.limit + 1)
        )
        if page.cursor is not None:
            position = decode_cursor(page.cursor)
            stmt = stmt.where(tuple_(created_at, identifier) < (position.created_at, position.id))

        rows = (await session.scalars(stmt)).all()
        items = list(rows[: page.limit])
        if len(rows) <= page.limit:
            return Page(items=items, next_cursor=None)

        last = cast(_KeysetRow, items[-1])
        return Page(items=items, next_cursor=encode_cursor(last.created_at, last.id))
