"""Кодек курсора и параметры страницы."""

import base64
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.kernel.errors import ValidationFailed
from app.kernel.pagination import Page, PageParams, decode_cursor, encode_cursor


def _cursor_of(raw: str) -> str:
    """Собрать курсор из произвольной строки, минуя encode_cursor."""
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def test_round_trip_keeps_microseconds() -> None:
    moment = datetime(2024, 3, 1, 12, 30, 45, 123456, tzinfo=UTC)
    identifier = uuid4()

    restored = decode_cursor(encode_cursor(moment, identifier))

    assert restored.created_at == moment
    assert restored.created_at.microsecond == 123456
    assert restored.id == identifier


def test_round_trip_keeps_offset() -> None:
    moment = datetime(2024, 3, 1, 12, 30, 45, 654321, tzinfo=timezone(timedelta(hours=3)))

    restored = decode_cursor(encode_cursor(moment, uuid4()))

    assert restored.created_at == moment
    assert restored.created_at.utcoffset() == timedelta(hours=3)


def test_cursor_is_url_safe() -> None:
    cursor = encode_cursor(datetime(2024, 3, 1, tzinfo=UTC), uuid4())

    assert "+" not in cursor
    assert "/" not in cursor
    assert "=" not in cursor


def test_encode_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        encode_cursor(datetime(2024, 3, 1, 12, 0, 0), uuid4())  # noqa: DTZ001


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "!!!!",
        "не base64",
        "zzz",
        _cursor_of("no separator here"),
        _cursor_of("2024-03-01T12:00:00+00:00"),
        _cursor_of("not-a-date|" + str(uuid4())),
        _cursor_of("2024-03-01T12:00:00+00:00|not-a-uuid"),
        _cursor_of("2024-13-45T99:99:99+00:00|" + str(uuid4())),
        base64.urlsafe_b64encode(b"\xff\xfe\xfd").decode("ascii").rstrip("="),
    ],
)
def test_broken_cursor_is_client_error(cursor: str) -> None:
    """Мусор в query-параметре — 422, а не 500 и не голый ValueError."""
    with pytest.raises(ValidationFailed) as raised:
        decode_cursor(cursor)

    assert raised.value.status == 422
    assert raised.value.extra == {"cursor": cursor}


def test_naive_cursor_is_rejected() -> None:
    """Курсор без смещения сдвинул бы выборку на величину часового пояса."""
    forged = _cursor_of(f"2024-03-01T12:00:00.000001|{uuid4()}")

    with pytest.raises(ValidationFailed):
        decode_cursor(forged)


def test_page_params_defaults() -> None:
    params = PageParams()

    assert params.cursor is None
    assert params.limit == 50


@pytest.mark.parametrize("limit", [0, -1, 201])
def test_page_params_rejects_limit_out_of_range(limit: int) -> None:
    with pytest.raises(ValidationError):
        PageParams(limit=limit)


def test_page_carries_schemas() -> None:
    class Item(BaseModel):
        id: UUID

    identifier = uuid4()
    page = Page[Item].model_validate({"items": [{"id": str(identifier)}], "next_cursor": "next"})

    assert page.items == [Item(id=identifier)]
    assert page.next_cursor == "next"
