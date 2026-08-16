"""Любая ошибка API отдаётся как RFC 9457 problem+json."""

from uuid import UUID

import pytest
from fastapi import APIRouter

from app.api.errors import _describe
from app.kernel.config import settings
from app.kernel.errors import Conflict, NotFound
from app.kernel.registry import Module
from app.kernel.schemas import BaseRequest
from tests.asgi import app_client
from tests.logs import capture_logs

PROBLEM_JSON = "application/problem+json"

OWNER_ID = UUID("018f5b4c-0000-7000-8000-000000000001")


class WidgetRequest(BaseRequest):
    name: str
    quantity: int


def widgets_module() -> Module:
    """Модуль с ручками, которые умеют падать всеми интересными способами."""
    router = APIRouter()

    @router.get("/widgets/{widget_id}")
    async def read_widget(widget_id: str) -> dict[str, str]:
        raise NotFound(f"Widget {widget_id} does not exist", widget_id=widget_id)

    @router.post("/widgets")
    async def create_widget(payload: WidgetRequest) -> dict[str, str]:
        return {"name": payload.name}

    @router.get("/widgets/{widget_id}/rename")
    async def rename_widget(widget_id: str) -> dict[str, str]:
        raise Conflict(
            f"Fields of widget {widget_id} are not patchable: owner",
            fields=["owner"],
            owner_id=OWNER_ID,
            status=999,
            request_id="spoofed",
            instance="/somewhere-else",
        )

    @router.get("/crash")
    async def crash() -> dict[str, str]:
        raise RuntimeError("kaboom: postgresql://app:secret@db/app")

    return Module(name="widgets", router=router, prefix="")


async def test_domain_error_is_problem_json() -> None:
    async with app_client([widgets_module()]) as client:
        response = await client.get("/widgets/42")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"] == f"{settings.errors_base_url}/not-found"
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["detail"] == "Widget 42 does not exist"
    assert body["instance"] == "/widgets/42"
    assert body["request_id"] == response.headers["x-request-id"]
    assert body["widget_id"] == "42"


async def test_extra_members_are_serialised_but_cannot_shadow_standard_ones() -> None:
    async with app_client([widgets_module()]) as client:
        response = await client.get("/widgets/7/rename")

    body = response.json()
    assert response.status_code == 409
    assert body["status"] == 409
    assert body["instance"] == "/widgets/7/rename"
    assert body["request_id"] != "spoofed"
    assert body["fields"] == ["owner"]
    assert body["owner_id"] == str(OWNER_ID)


@pytest.mark.parametrize(
    ("payload", "expected_loc"),
    [
        ({"name": "bolt"}, ["body", "quantity"]),
        ({"name": "bolt", "quantity": 1, "colour": "red"}, ["body", "colour"]),
    ],
)
async def test_fastapi_validation_error_uses_the_same_format(
    payload: dict[str, object],
    expected_loc: list[str],
) -> None:
    async with app_client([widgets_module()]) as client:
        response = await client.post("/widgets", json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"] == f"{settings.errors_base_url}/validation-failed"
    assert body["status"] == 422
    assert body["request_id"] == response.headers["x-request-id"]
    assert [violation["loc"] for violation in body["errors"]] == [expected_loc]
    assert set(body["errors"][0]) == {"loc", "msg", "type"}


async def test_unknown_path_is_problem_json() -> None:
    """404 фреймворка не должен отличаться по формату от доменного 404."""
    async with app_client([widgets_module()]) as client:
        response = await client.get("/nothing-here")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"] == f"{settings.errors_base_url}/not-found"
    assert body["instance"] == "/nothing-here"
    assert body["request_id"] == response.headers["x-request-id"]
    assert "detail" in body


async def test_wrong_method_is_problem_json_and_keeps_allow_header() -> None:
    async with app_client([widgets_module()]) as client:
        response = await client.delete("/widgets/42")

    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["allow"] == "GET"
    body = response.json()
    assert body["type"] == f"{settings.errors_base_url}/method-not-allowed"
    assert body["title"] == "Method Not Allowed"
    assert body["request_id"] == response.headers["x-request-id"]


async def test_unhandled_exception_leaks_nothing() -> None:
    async with app_client([widgets_module()], raise_app_exceptions=False) as client:
        response = await client.get("/crash")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body == {
        "type": f"{settings.errors_base_url}/internal-error",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "Internal server error",
        "instance": "/crash",
        "request_id": response.headers["x-request-id"],
    }
    assert "kaboom" not in response.text
    assert "secret" not in response.text
    assert "RuntimeError" not in response.text


def test_non_standard_status_gets_a_generic_description() -> None:
    """Статус, которого нет в HTTPStatus, не должен ронять обработчик ошибок."""
    assert _describe(599) == ("http-error", "HTTP Error")
    assert _describe(404) == ("not-found", "Not Found")
    assert _describe(413) == ("request-entity-too-large", "Request Entity Too Large")


async def test_unhandled_exception_is_logged_with_traceback() -> None:
    with capture_logs() as stream:
        async with app_client([widgets_module()], raise_app_exceptions=False) as client:
            await client.get("/crash")

    output = stream.getvalue()
    assert "http.unhandled_error" in output
    assert "RuntimeError" in output
    assert "Traceback (most recent call last)" in output
