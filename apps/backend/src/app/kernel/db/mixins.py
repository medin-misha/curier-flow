"""Миксины колонок, общих для большинства таблиц.

Миксины, а не общий базовый класс с колонками: набор нужных полей у таблиц
разный, а единственная иерархия заставила бы тащить `deleted_at` в справочники
и журналы, где мягкое удаление бессмысленно.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7


class UUIDPkMixin:
    """Первичный ключ UUIDv7.

    UUIDv7 в отличие от v4 монотонен по времени: соседние по времени вставки
    попадают в соседние страницы B-tree, индекс не фрагментируется. В отличие
    от serial ключ генерируется на стороне приложения — id известен до вставки
    и не выдаёт объём таблицы наружу.

    Берётся из `uuid_utils.compat`, а не из `uuid_utils`: нативная функция
    возвращает собственный тип, несовместимый с `uuid.UUID`, на котором
    завязаны и SQLAlchemy, и Pydantic.
    """

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    """Метки создания и последнего изменения.

    Значения проставляет БД (`now()`), а не Python: время берётся из одного
    источника, одинакового для всех процессов приложения и для ручных правок
    через psql.
    """

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """Мягкое удаление: строка остаётся, но считается удалённой.

    Нужен там, где на запись ссылаются журналы и внешние системы и физическое
    удаление порвало бы историю. Фильтрация по `deleted_at IS NULL` — забота
    сервиса: неявный глобальный фильтр слишком легко обойти и слишком трудно
    отключить там, где нужны все строки.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
