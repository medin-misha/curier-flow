"""Импорт на PostgreSQL: прогноз, статусы, повторы, гонки и граница записи."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.kernel.db import session as db
from app.kernel.events.models import OutboxMessage
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.courier_module.models import Courier, CourierPlatformAccount
from app.modules.courier_module.module import courier_module
from app.modules.courier_module.services import imports
from tests.asgi import app_client


def record(row: int = 2, **updates: Any) -> dict[str, Any]:
    return {
        "source_row": row,
        "legacy_id": f"legacy-{row}",
        "courier": {
            "full_name": "Imported Courier",
            "email": f"courier{row}@example.com",
            "phone": f"+42077700{row:04d}",
            "date_of_birth": "1990-02-03",
            "created_at": "2024-01-02T03:04:05+00:00",
            "consent_to_processing": True,
            "platform_accounts": [
                {"platform": "bolt_food", "status": "active"},
                {"platform": "foodora", "status": "inactive"},
            ],
            **updates,
        },
    }


def batch(*records: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "couriers": list(records)}


@pytest.fixture
async def client(clean_db: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    async with db.session_factory() as session, session.begin():
        await session.execute(delete(Courier))
    async with app_client([courier_module], raise_app_exceptions=False) as http:
        token = issue_tokens(UUID(int=103), settings=jwt_settings, claims={"kind": "admin"})
        http.headers["authorization"] = f"Bearer {token.access_token}"
        yield http


async def counts() -> tuple[int, int, int]:
    async with db.session_factory() as session:
        values = [
            int(await session.scalar(select(func.count()).select_from(model)) or 0)
            for model in (Courier, CourierPlatformAccount, OutboxMessage)
        ]
        return values[0], values[1], values[2]


async def test_preview_simulates_duplicates_and_split_without_writes(client: AsyncClient) -> None:
    payload = batch(
        record(),
        record(3),
        record(4, email="courier2@example.com", phone="+420999888777"),
        record(5, email="courier2@example.com", phone=record(3)["courier"]["phone"]),
    )
    response = await client.post("/import-courier", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["dry_run"] is True
    assert result["would_create_count"] == 2
    assert result["existing_count"] == 1
    assert result["conflict_count"] == 1
    assert result["results"][-1]["reason"] == "identity-split"
    assert all(row["courier_id"] is None for row in result["results"])
    assert await counts() == (0, 0, 0)

    imported = await client.post("/import-courier?dry_run=false", json=payload)
    assert imported.status_code == 200, imported.text
    assert imported.json()["created_count"] == 2
    assert imported.json()["existing_count"] == 1
    assert imported.json()["conflict_count"] == 1


async def test_import_preserves_status_date_and_never_overwrites_repeat(
    client: AsyncClient,
) -> None:
    first = await client.post("/import-courier?dry_run=false", json=batch(record()))
    assert first.status_code == 200, first.text
    courier_id = first.json()["results"][0]["courier_id"]
    assert first.json()["created_count"] == 1
    original = (await client.get(f"/courier/{courier_id}")).json()
    assert original["created_at"] == "2024-01-02T03:04:05Z"
    assert {row["platform"]: row["status"] for row in original["platform_accounts"]} == {
        "bolt_food": "active",
        "foodora": "inactive",
    }
    assert original["consent_at"] is not None
    for updates in (
        {"email": " COURIER2@EXAMPLE.COM ", "phone": "+420999888777"},
        {"email": "other@example.com", "phone": "+420 (777)-000-002"},
    ):
        retry = await client.post(
            "/import-courier?dry_run=false",
            json=batch(
                record(
                    3,
                    full_name="Must not overwrite",
                    platform_accounts=[
                        {"platform": "wolt", "status": "problem"},
                    ],
                    **updates,
                )
            ),
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["existing_count"] == 1
        assert retry.json()["results"][0]["courier_id"] == courier_id
    assert (await client.get(f"/courier/{courier_id}")).json() == original
    assert await counts() == (1, 2, 1)
    async with db.session_factory() as session:
        topics = list((await session.scalars(select(OutboxMessage.topic))).all())
    assert topics == ["courier.profile_changed"]


async def test_conflict_is_reported_while_other_rows_commit(client: AsyncClient) -> None:
    first, second = record(), record(3)
    await client.post("/import-courier?dry_run=false", json=batch(first, second))
    rows = batch(
        record(4, email=first["courier"]["email"], phone=second["courier"]["phone"]),
        record(5, consent_to_processing=False),
    )
    preview = (await client.post("/import-courier", json=rows)).json()
    imported = (await client.post("/import-courier?dry_run=false", json=rows)).json()
    assert preview["conflict_count"] == imported["conflict_count"] == 1
    assert imported["created_count"] == 1
    assert imported["results"][0]["reason"] == "identity-split"
    assert await counts() == (3, 6, 3)
    courier_id = imported["results"][1]["courier_id"]
    assert (await client.get(f"/courier/{courier_id}")).json()["consent_at"] is None


async def test_parallel_import_creates_one_courier(client: AsyncClient) -> None:
    first, second = await asyncio.gather(
        client.post("/import-courier?dry_run=false", json=batch(record())),
        client.post("/import-courier?dry_run=false", json=batch(record())),
    )
    assert first.status_code == second.status_code == 200
    assert sorted([first.json()["created_count"], second.json()["created_count"]]) == [0, 1]
    assert first.json()["results"][0]["courier_id"] == second.json()["results"][0]["courier_id"]
    assert await counts() == (1, 2, 1)


async def test_unexpected_error_rolls_back_entire_batch(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = imports._import_record

    async def fail_second(item: Any, *, session: Any) -> Any:
        if item.source_row == 3:
            raise RuntimeError("refused second record")
        return await original(item, session=session)

    monkeypatch.setattr(imports, "_import_record", fail_second)
    response = await client.post("/import-courier?dry_run=false", json=batch(record(), record(3)))
    assert response.status_code == 500
    assert await counts() == (0, 0, 0)


@pytest.mark.parametrize(
    "updates",
    [
        {"phone": "123"},
        {"date_of_birth": None},
        {"created_at": "2024-01-02T03:04:05"},
        {"platform_accounts": [{"platform": "wolt", "status": "unknown"}]},
        {"documents": []},
    ],
)
async def test_invalid_batch_never_writes(client: AsyncClient, updates: dict[str, Any]) -> None:
    response = await client.post(
        "/import-courier?dry_run=false",
        json=batch(record(), record(3, **updates)),
    )
    assert response.status_code == 422, response.text
    assert await counts() == (0, 0, 0)


async def test_import_requires_admin_token(client: AsyncClient) -> None:
    client.headers.pop("authorization")
    response = await client.post("/import-courier", json=batch(record()))
    assert response.status_code == 401
    token = issue_tokens(UUID(int=104), settings=jwt_settings, claims={"kind": "courier"})
    response = await client.post(
        "/import-courier?dry_run=false",
        json=batch(record()),
        headers={"authorization": f"Bearer {token.access_token}"},
    )
    assert response.status_code == 401
    assert await counts() == (0, 0, 0)
