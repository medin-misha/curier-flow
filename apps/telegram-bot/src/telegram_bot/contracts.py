"""Межсервисный payload регистрации курьера."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, StringConstraints

SIGNED_INT64_MAX = (1 << 63) - 1

type FullName = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=255),
]
type ContactPlatform = Annotated[
    StrictStr,
    StringConstraints(max_length=32),
]
type Contact = Annotated[
    StrictStr,
    StringConstraints(max_length=255),
]
type Platform = Literal["bolt_food", "foodora", "wolt"]


class CourierRegistrationNotification(BaseModel):
    """Строгий пяти-полевый контракт queue message."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    telegram_id: StrictInt = Field(gt=0, le=SIGNED_INT64_MAX)
    full_name: FullName
    contact_platform: ContactPlatform | None
    contact: Contact | None
    platform: Platform
