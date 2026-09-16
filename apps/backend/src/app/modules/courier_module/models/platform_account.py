"""Таблица `courier_platform_accounts`: регистрации курьера на платформах."""

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.modules.courier_module.models.courier import Courier


class DeliveryPlatform(StrEnum):
    """Поддерживаемые delivery-платформы."""

    BOLT_FOOD = "bolt_food"
    FOODORA = "foodora"
    WOLT = "wolt"


class PlatformAccountStatus(StrEnum):
    """Состояние регистрации курьера на delivery-платформе."""

    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROBLEM = "problem"


def _enum_values(enum: type[StrEnum]) -> list[str]:
    """Вернуть строковые значения enum для VARCHAR-колонки."""
    return [member.value for member in enum]


class CourierPlatformAccount(UUIDPkMixin, TimestampMixin, Base):
    """Одна регистрация Courier на одной delivery-платформе."""

    __tablename__ = "courier_platform_accounts"
    __patchable__ = frozenset({"status"})
    __table_args__ = (UniqueConstraint("courier_id", "platform"),)

    courier_id: Mapped[UUID] = mapped_column(ForeignKey("couriers.id", ondelete="CASCADE"))
    platform: Mapped[DeliveryPlatform] = mapped_column(
        Enum(
            DeliveryPlatform,
            name="delivery_platform",
            native_enum=False,
            length=32,
            values_callable=_enum_values,
        ),
        index=True,
    )
    status: Mapped[PlatformAccountStatus] = mapped_column(
        Enum(
            PlatformAccountStatus,
            name="platform_account_status",
            native_enum=False,
            length=16,
            values_callable=_enum_values,
        ),
        default=PlatformAccountStatus.PENDING,
        index=True,
    )

    courier: Mapped["Courier"] = relationship(back_populates="platform_accounts")


Index(
    "ix_courier_platform_accounts_keyset",
    CourierPlatformAccount.created_at.desc(),
    CourierPlatformAccount.id.desc(),
)
Index(
    "ix_courier_platform_accounts_courier_keyset",
    CourierPlatformAccount.courier_id,
    CourierPlatformAccount.created_at.desc(),
    CourierPlatformAccount.id.desc(),
)
