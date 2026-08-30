"""Объектное хранилище: подпись без сети и операции против настоящего MinIO."""

import asyncio
import urllib.parse
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError

from app.platform.s3 import (
    ObjectStorage,
    ObjectTooLargeError,
    S3Settings,
    s3_settings,
    storage,
)

#: Заведомо закрытый порт: клиент, который полез бы в сеть, упал бы сразу.
UNREACHABLE = "http://127.0.0.1:1"


@pytest.fixture
async def offline() -> AsyncIterator[ObjectStorage]:
    """Хранилище по недоступному адресу: годится только для подписи ссылок."""
    async with storage(S3Settings(endpoint_url=UNREACHABLE, bucket="files")) as client:
        yield client


@pytest.fixture
async def bucket(minio_endpoint: str) -> AsyncIterator[ObjectStorage]:
    """Свежий бакет в контейнере на один тест."""
    config = S3Settings(endpoint_url=minio_endpoint, bucket=f"test-{uuid4().hex[:8]}")
    async with storage(config) as client:
        await client.client.create_bucket(Bucket=config.bucket)
        yield client


def query_of(url: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


async def put(client: ObjectStorage, key: str, body: bytes, content_type: str) -> None:
    await client.client.put_object(
        Bucket=client.bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )


def test_settings_match_the_env_example() -> None:
    assert s3_settings.bucket == "app-files"
    assert s3_settings.presign_ttl == 900
    assert s3_settings.region == "us-east-1"
    assert s3_settings.public_endpoint_url == ""


async def test_links_are_signed_for_the_public_endpoint(minio_endpoint: str) -> None:
    """Ссылка обязана вести туда, куда придёт клиент, и оттуда же работать.

    Подпись SigV4 накрывает Host: подписанная на внутренний адрес ссылка в
    браузере отдала бы SignatureDoesNotMatch, а подменить хост в готовой
    ссылке нельзя — подпись перестанет сходиться.
    """
    config = S3Settings(
        # «Внутренний» адрес заведомо мёртвый: если по нему пойдёт хоть один
        # запрос, тест это заметит. Ссылки при этом обязаны работать.
        endpoint_url=UNREACHABLE,
        public_endpoint_url=minio_endpoint,
        bucket=f"public-{uuid4().hex[:8]}",
    )
    async with storage(S3Settings(endpoint_url=minio_endpoint, bucket=config.bucket)) as real:
        await real.client.create_bucket(Bucket=config.bucket)

    async with storage(config) as client:
        url = await client.presigned_put("uploads/a.txt", content_type="text/plain")
        async with httpx.AsyncClient() as http:
            uploaded = await http.put(url, content=b"ok", headers={"content-type": "text/plain"})

    assert url.startswith(minio_endpoint)
    assert uploaded.status_code == 200


async def test_presign_does_not_touch_the_network(
    offline: ObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ссылка выдаётся рядом с открытой транзакцией: сети там быть не должно."""

    async def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("presigning must be computed locally")

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "create_connection", refuse)

    upload = await offline.presigned_put("docs/report.pdf", content_type="application/pdf")
    download = await offline.presigned_get("docs/report.pdf")

    assert upload.startswith(f"{UNREACHABLE}/files/docs/report.pdf?")
    assert query_of(upload)["X-Amz-Algorithm"] == "AWS4-HMAC-SHA256"
    assert query_of(download)["X-Amz-Expires"] == "900"


async def test_presigned_put_signs_the_content_type(offline: ObjectStorage) -> None:
    """Тип попадает в подпись, иначе клиент зальёт что угодно под любым типом."""
    signed = query_of(await offline.presigned_put("a.png", content_type="image/png"))
    unsigned = query_of(await offline.presigned_put("a.png"))

    assert "content-type" in signed["X-Amz-SignedHeaders"]
    assert "content-type" not in unsigned["X-Amz-SignedHeaders"]


async def test_presigned_get_sets_the_download_name(offline: ObjectStorage) -> None:
    url = await offline.presigned_get("a1b2c3", download_name="отчёт.pdf")

    assert query_of(url)["response-content-disposition"] == 'attachment; filename="отчёт.pdf"'


async def test_expiry_can_be_overridden(offline: ObjectStorage) -> None:
    url = await offline.presigned_get("a.png", expires_in=60)

    assert query_of(url)["X-Amz-Expires"] == "60"


async def test_head_returns_metadata_of_an_existing_object(bucket: ObjectStorage) -> None:
    await put(bucket, "docs/report.pdf", b"hello world", "application/pdf")

    info = await bucket.head_object("docs/report.pdf")

    assert info is not None
    assert (info.size, info.content_type) == (11, "application/pdf")
    assert info.etag and '"' not in info.etag


async def test_head_of_a_missing_object_is_none(bucket: ObjectStorage) -> None:
    """Отсутствие объекта — ответ на вопрос, а не сбой хранилища."""
    assert await bucket.head_object("docs/never-uploaded.pdf") is None


async def test_read_returns_bounded_content_and_metadata(bucket: ObjectStorage) -> None:
    await put(bucket, "docs/template.docx", b"document", "application/docx")

    downloaded = await bucket.read_object("docs/template.docx", max_size=8)

    assert downloaded is not None
    assert downloaded.body == b"document"
    assert downloaded.info.size == 8
    assert downloaded.info.content_type == "application/docx"


async def test_read_handles_missing_and_oversized_objects(bucket: ObjectStorage) -> None:
    await put(bucket, "docs/large.docx", b"too large", "application/docx")

    assert await bucket.read_object("docs/missing.docx", max_size=8) is None
    with pytest.raises(ObjectTooLargeError) as raised:
        await bucket.read_object("docs/large.docx", max_size=8)

    assert (raised.value.size, raised.value.max_size) == (9, 8)


async def test_read_requires_a_positive_limit(bucket: ObjectStorage) -> None:
    with pytest.raises(ValueError, match="max_size must be positive"):
        await bucket.read_object("docs/template.docx", max_size=0)


async def test_head_reraises_a_real_storage_failure(minio_endpoint: str) -> None:
    """Отказ хранилища нельзя выдавать за «объекта нет»."""
    broken = S3Settings(endpoint_url=minio_endpoint, secret_key="wrong", bucket="whatever")  # noqa: S106
    async with storage(broken) as client:
        with pytest.raises(ClientError):
            await client.head_object("docs/report.pdf")


async def test_delete_removes_the_object_and_tolerates_a_repeat(bucket: ObjectStorage) -> None:
    await put(bucket, "tmp/a.bin", b"x", "application/octet-stream")

    await bucket.delete_object("tmp/a.bin")
    await bucket.delete_object("tmp/a.bin")

    assert await bucket.head_object("tmp/a.bin") is None


async def test_list_prefix_returns_only_matching_keys(bucket: ObjectStorage) -> None:
    await put(bucket, "uploads/a.txt", b"aa", "text/plain")
    await put(bucket, "uploads/b.txt", b"bbb", "text/plain")
    await put(bucket, "archive/c.txt", b"c", "text/plain")

    entries = await bucket.list_prefix("uploads/")

    assert sorted((entry.key, entry.size) for entry in entries) == [
        ("uploads/a.txt", 2),
        ("uploads/b.txt", 3),
    ]


async def test_list_prefix_respects_the_limit(bucket: ObjectStorage) -> None:
    for index in range(3):
        await put(bucket, f"uploads/{index}.txt", b"x", "text/plain")

    assert len(await bucket.list_prefix("uploads/", limit=2)) == 2


async def test_list_prefix_of_an_empty_prefix_is_empty(bucket: ObjectStorage) -> None:
    assert await bucket.list_prefix("nothing/") == []


async def test_presigned_url_actually_works(bucket: ObjectStorage, minio_endpoint: str) -> None:
    """Подпись считается локально, но принимать её должно настоящее хранилище."""
    url = await bucket.presigned_put("uploads/signed.txt", content_type="text/plain")
    async with httpx.AsyncClient() as http:
        uploaded = await http.put(url, content=b"signed", headers={"content-type": "text/plain"})
        assert uploaded.status_code == 200

        downloaded = await http.get(await bucket.presigned_get("uploads/signed.txt"))

    assert minio_endpoint in url
    assert downloaded.status_code == 200
    assert downloaded.content == b"signed"
