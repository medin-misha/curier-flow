"""Декларативная база SQLAlchemy для всех моделей приложения."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase

#: Явные шаблоны имён для индексов и ограничений. Без них Postgres придумывает
#: имена сам, autogenerate Alembic не может на них сослаться, и в downgrade
#: ограничение оказывается невозможно удалить.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Общий предок ORM-моделей.

    `__patchable__` — белый список полей, которые клиент вправе менять через
    PATCH. Он живёт на модели, а не на схеме запроса, потому что защищает
    именно строку в БД: одна и та же схема может прийти из разных мест, а
    правило «status меняет только сервис» должно быть одно.

    Пустой список по умолчанию означает «патчить нечего»: разрешение выдаётся
    явно, а не забывается по умолчанию.
    """

    __patchable__: ClassVar[frozenset[str]] = frozenset()

    #: Значения, вычисленные сервером БД (`now()` в created_at и updated_at),
    #: забираются тем же запросом через RETURNING. Иначе после flush атрибут
    #: остаётся просроченным, и первое же обращение к нему уходит в ленивую
    #: подгрузку — в async-коде это не лишний запрос, а MissingGreenlet.
    #: Модель, переопределяющая __mapper_args__, обязана сохранить этот ключ.
    #: ClassVar здесь недопустим: SQLAlchemy объявляет атрибут как переменную
    #: экземпляра, и mypy запрещает сузить её до переменной класса.
    __mapper_args__: Any = {"eager_defaults": True}  # noqa: RUF012

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    #: Все временные метки хранятся с таймзоной. Иначе значение зависит от
    #: часового пояса сессии Postgres, а сравнение с aware-datetime из Python
    #: падает в рантайме.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
    }
