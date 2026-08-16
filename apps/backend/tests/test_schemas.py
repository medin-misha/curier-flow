"""Базовые схемы: запрет лишних полей и сборка ответа из ORM-объекта."""

import pytest
from pydantic import ValidationError

from app.kernel.schemas import BaseRequest, BaseResponse


class Command(BaseRequest):
    name: str


class View(BaseResponse):
    name: str


def test_unknown_field_is_rejected() -> None:
    """Опечатка в имени поля обязана быть видна клиенту, а не потеряться."""
    with pytest.raises(ValidationError):
        Command.model_validate({"name": "ok", "nmae": "typo"})


def test_known_fields_pass() -> None:
    assert Command.model_validate({"name": "ok"}).name == "ok"


def test_response_is_built_from_attributes() -> None:
    class Row:
        name = "from-orm"

    assert View.model_validate(Row()).name == "from-orm"
