"""Частичный поиск: HTTP-контракт и реальная PostgreSQL выборка."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.kernel.db import session as session_module
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.courier_module.models import (
    Courier,
    CourierPlatformAccount,
    DeliveryPlatform,
    PlatformAccountStatus,
)
from app.modules.courier_module.module import courier_module
from tests.asgi import app_client


@pytest.fixture
async def search_client(clean_db: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(Courier))
        for index, (name, email, phone, status) in enumerate(
            [
                ("Eva Novak", "eva.novak@example.com", "+420777111222", "active"),
                ("Adam Novak", "adam@example.com", "+420777333444", "pending"),
                ("Иван Петров", "other@example.com", "+420777555666", "active"),
                ("Literal % / Person", "percent@example.com", "+420777888001", "pending"),
                ("Literal _ Person", "underscore@example.com", "+420777888002", "pending"),
            ],
            1,
        ):
            session.add(
                Courier(
                    id=UUID(int=index),
                    full_name=name,
                    email=email,
                    phone=phone,
                    date_of_birth=datetime(1990, 1, 1, tzinfo=UTC).date(),
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    platform_accounts=[
                        CourierPlatformAccount(
                            platform=DeliveryPlatform.WOLT, status=PlatformAccountStatus(status)
                        ),
                        CourierPlatformAccount(
                            platform=DeliveryPlatform.FOODORA, status=PlatformAccountStatus.PROBLEM
                        ),
                    ],
                )
            )
    async with app_client([courier_module]) as client:
        access = issue_tokens(
            UUID(int=103), settings=jwt_settings, claims={"kind": "admin"}
        ).access_token
        client.headers["authorization"] = f"Bearer {access}"
        yield client


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Eva", {1}),
        ("ив", {3}),
        ("ПЕТР", {3}),
        ("/", {4}),
        (" -() ", set()),
        ("nov", {1, 2}),
        ("oVa", {1, 2}),
        ("111", {1}),
        ("777 (111)-222", {1}),
        ("420777111", {1}),
        ("+420 (777) 111-222", {1}),
        ("NOVAK@EXAM", {1}),
        ("", {1, 2, 3, 4, 5}),
        ("   ", {1, 2, 3, 4, 5}),
        ("unmatched", set()),
        ("%", {4}),
        ("_", {5}),
    ],
)
async def test_partial_query(search_client: AsyncClient, query: str, expected: set[int]) -> None:
    response = await search_client.get("/courier", params={"query": query})
    assert response.status_code == 200, response.text
    assert {UUID(item["id"]).int for item in response.json()["items"]} == expected


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"status": "active"}, {1}),
        ({"status": "problem"}, {1, 2}),
        ({"email": "adam@example.com"}, {2}),
        ({"phone": "+420777111222"}, {1}),
        ({"full_name": "Adam Novak"}, {2}),
        ({"full_name": "Adam"}, set()),
        ({"email": "other@example.com"}, set()),
    ],
)
async def test_query_combines_exact_filters(
    search_client: AsyncClient, extra: dict[str, str], expected: set[int]
) -> None:
    response = await search_client.get("/courier", params={"query": "nov", **extra})
    assert response.status_code == 200, response.text
    assert {UUID(item["id"]).int for item in response.json()["items"]} == expected


async def test_filtered_keyset(search_client: AsyncClient) -> None:
    ids: list[int] = []
    cursor = None
    for _ in range(4):
        params = {"query": "nov", "limit": "1"}
        if cursor:
            params["cursor"] = cursor
        response = await search_client.get("/courier", params=params)
        assert response.status_code == 200, response.text
        ids.extend(UUID(item["id"]).int for item in response.json()["items"])
        cursor = response.json()["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert ids == [2, 1]


async def test_query_validation_and_authorization(search_client: AsyncClient) -> None:
    assert (await search_client.get("/courier", params={"query": "a" * 320})).status_code == 200
    assert (await search_client.get("/courier", params={"query": "a" * 321})).status_code == 422


async def test_query_requires_authorization(search_client: AsyncClient) -> None:
    search_client.headers.pop("authorization")
    assert (await search_client.get("/courier", params={"query": "nov"})).status_code == 401
