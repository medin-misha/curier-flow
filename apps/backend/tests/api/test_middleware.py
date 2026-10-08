"""Идентификатор запроса проходит насквозь: заголовок → контекст → лог → ответ."""

import json
from typing import Any
from uuid import UUID

import pytest
from fastapi import APIRouter
from starlette.types import Message, Scope

from app.api.middleware import RequestContextMiddleware
from app.kernel.registry import Module
from tests.asgi import app_client
from tests.logs import capture_logs


def ping_module() -> Module:
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/crash")
    async def crash() -> dict[str, str]:
        raise RuntimeError("kaboom")

    return Module(name="ping", router=router, prefix="")


def access_log(output: str) -> dict[str, Any]:
    """Единственная запись о запросе среди прочих строк лога."""
    records: list[dict[str, Any]] = [json.loads(line) for line in output.splitlines() if line]
    requests = [record for record in records if record["event"] == "http.request"]
    assert len(requests) == 1
    return requests[0]


async def test_incoming_request_id_reaches_log_and_response() -> None:
    with capture_logs() as stream:
        async with app_client([ping_module()]) as client:
            response = await client.get("/ping", headers={"X-Request-ID": "trace-123"})

    record = access_log(stream.getvalue())
    assert response.headers["x-request-id"] == "trace-123"
    assert record["request_id"] == "trace-123"
    assert record["method"] == "GET"
    assert record["path"] == "/ping"
    assert record["status"] == 200
    assert record["duration_ms"] >= 0


async def test_request_id_is_generated_when_absent() -> None:
    with capture_logs() as stream:
        async with app_client([ping_module()]) as client:
            response = await client.get("/ping")

    generated = response.headers["x-request-id"]
    assert UUID(generated).version == 7
    assert access_log(stream.getvalue())["request_id"] == generated


@pytest.mark.parametrize("unsafe", ["bad value!", "x" * 129, "", "id;drop table"])
async def test_unsafe_incoming_request_id_is_replaced(unsafe: str) -> None:
    """Чужое значение попадает в логи и заголовки, поэтому проверяется."""
    async with app_client([ping_module()]) as client:
        response = await client.get("/ping", headers={"X-Request-ID": unsafe})

    assert response.headers["x-request-id"] != unsafe
    assert UUID(response.headers["x-request-id"]).version == 7


async def test_non_http_scopes_pass_through_untouched() -> None:
    """В lifespan и websocket нет ни метода, ни пути — трогать их нельзя."""
    seen: list[Scope] = []

    async def downstream(scope: Scope, _receive: object, _send: object) -> None:
        seen.append(scope)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}  # pragma: no cover

    async def send(_message: Message) -> None: ...  # pragma: no cover

    await RequestContextMiddleware(downstream)({"type": "lifespan"}, receive, send)

    assert seen == [{"type": "lifespan"}]


async def test_response_to_failed_request_still_carries_the_header() -> None:
    with capture_logs() as stream:
        async with app_client([ping_module()], raise_app_exceptions=False) as client:
            response = await client.get("/crash", headers={"X-Request-ID": "trace-500"})

    record = access_log(stream.getvalue())
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "trace-500"
    assert response.json()["request_id"] == "trace-500"
    assert record["status"] == 500
    assert record["level"] == "error"
