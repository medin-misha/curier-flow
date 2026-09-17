"""Локальная проекция контактов курьера для чтения истории аренды."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base


class TransportCourierProfile(Base):
    """Версионированный контакт; удаление оставляет только защитную отметку."""

    __tablename__ = "transport_courier_profiles"
    __table_args__ = (
        CheckConstraint(
            "(is_deleted AND full_name IS NULL AND phone IS NULL) OR "
            "(NOT is_deleted AND full_name IS NOT NULL AND phone IS NOT NULL)",
            name="profile_state",
        ),
    )

    courier_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(16))
    source_updated_at: Mapped[datetime] = mapped_column()
    is_deleted: Mapped[bool] = mapped_column(default=False)
