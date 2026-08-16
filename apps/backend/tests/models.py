"""ORM-модели, существующие только ради тестов ядра.

Живут в `tests/`, а не в `src/`: это полигон для проверки миксинов, CRUD и
пагинации, в поставку шаблона такие таблицы попадать не должны.
"""

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Widget(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Полноценная сущность: все миксины и непустой белый список патча."""

    __tablename__ = "test_widgets"
    __patchable__ = frozenset({"name", "quantity"})
    # Индекс под keyset: порядок колонок и направление обязаны совпадать
    # с ORDER BY в CRUD.list_page, иначе Postgres пойдёт сортировкой.
    __table_args__ = (Index("ix_test_widgets_keyset", text("created_at DESC, id DESC")),)

    name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(default=0)
    owner: Mapped[str] = mapped_column(String(50), default="system")


class Blob(UUIDPkMixin, Base):
    """Сущность без `created_at` и с пустым `__patchable__` по умолчанию."""

    __tablename__ = "test_blobs"

    payload: Mapped[str] = mapped_column(String(100))
