"""Модуль storage: двухфазная загрузка, проверка объекта и уборка.

Главное свойство модуля, которое здесь сторожится, — внешний I/O за пределами
транзакции. Фикстура `guard_transactions` подменяет методы `ObjectStorage`
обёрткой, которая падает, если в момент вызова хоть у одной сессии открыта
транзакция; она autouse, поэтому проверка действует во всех тестах модуля.
Что сторож не вхолостую, доказывает
`test_s3_calls_never_happen_inside_a_transaction`.

MinIO и Postgres настоящие: подпись, `head_object` и `SKIP LOCKED` проверяются
только против них.
"""

import dataclasses
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.kernel.db import session as session_module
from app.kernel.events.models import OutboxMessage
from app.kernel.pagination import PageParams
from app.main import create_app
from app.modules import MODULES
from app.modules.storage import tasks as storage_tasks
from app.modules.storage.models import File, FileStatus
from app.modules.storage.module import storage_lifespan, storage_module
from app.modules.storage.schemas.requests import ConfirmRequest
from app.modules.storage.services import (
    FileStorage,
    StorageSettings,
    confirm_upload,
    delete_marked,
    list_files,
    sweep_orphans,
)
from app.platform.s3 import ObjectStorage, S3Settings, storage
from app.platform.taskiq import SCHEDULE_ATTR, task_name
from tests.asgi import app_client

#: Лимиты меньше боевых: файл на килобайт заливается мгновенно, а превышение
#: лимита проверяется без мегабайтов трафика в тесте.
LIMITS: Final = StorageSettings(
    max_file_size=1024,
    allowed_content_types=frozenset({"image/png", "text/plain"}),
    orphan_ttl=600,
    batch_size=10,
)

PNG: Final = "image/png"


@dataclass
class TransactionWatch:
    """Сессии, которые хоть раз открывали транзакцию в этом тесте."""

    sessions: list[Session] = field(default_factory=list)

    def open_now(self) -> list[Session]:
        """Те из них, у кого транзакция открыта прямо сейчас."""
        return [session for session in self.sessions if session.in_transaction()]


def guarded(method: Any, name: str, watch: TransactionWatch) -> Any:
    """Обернуть метод хранилища проверкой «транзакция закрыта»."""

    async def call(self: ObjectStorage, *args: Any, **kwargs: Any) -> Any:
        assert not watch.open_now(), (
            f"ObjectStorage.{name} was called while a database transaction was open: "
            f"external I/O holds a pooled connection and row locks for as long as the "
            f"storage takes to answer"
        )
        return await method(self, *args, **kwargs)

    return call


@pytest.fixture(autouse=True)
def guard_transactions(monkeypatch: pytest.MonkeyPatch) -> Iterator[TransactionWatch]:
    """Запретить обращения к хранилищу при открытой транзакции."""
    watch = TransactionWatch()

    def track(session: Session, _transaction: Any, _connection: Any) -> None:
        watch.sessions.append(session)

    event.listen(Session, "after_begin", track)
    for name in (
        "head_object",
        "delete_object",
        "presigned_put",
        "presigned_get",
        "create_multipart_upload",
        "upload_part",
        "complete_multipart_upload",
        "abort_multipart_upload",
        "list_multipart_upload_ids",
        "abort_multipart_uploads_for_key",
    ):
        monkeypatch.setattr(ObjectStorage, name, guarded(getattr(ObjectStorage, name), name, watch))
    yield watch
    event.remove(Session, "after_begin", track)


@contextmanager
def failing_commit() -> Iterator[None]:
    """Ронять транзакцию после того, как её запросы уже ушли в базу."""

    def boom(_session: Session, _flush_context: Any) -> None:
        raise RuntimeError("commit refused")

    event.listen(Session, "after_flush", boom)
    try:
        yield
    finally:
        event.remove(Session, "after_flush", boom)


@pytest.fixture
async def bucket(minio_endpoint: str) -> AsyncIterator[S3Settings]:
    """Свежий бакет в контейнере на один тест."""
    config = S3Settings(endpoint_url=minio_endpoint, bucket=f"files-{uuid4().hex[:8]}")
    async with storage(config) as client:
        await client.client.create_bucket(Bucket=config.bucket)
    yield config


@pytest.fixture
async def files(bucket: S3Settings) -> AsyncIterator[FileStorage]:
    """Хранилище с лимитами модуля: им пользуются прямые вызовы сервиса."""
    async with storage(bucket) as objects:
        yield FileStorage(objects=objects, limits=LIMITS)


@pytest.fixture
async def sessions(clean_db: None) -> async_sessionmaker[AsyncSession]:  # noqa: ARG001
    """Фабрика сессий тестовой базы с уже очищенными таблицами."""
    return session_module.session_factory


@pytest.fixture
async def client(
    bucket: S3Settings,
    sessions: async_sessionmaker[AsyncSession],  # noqa: ARG001  # порядок: сперва чистая база
) -> AsyncIterator[AsyncClient]:
    """Клиент к приложению из одного модуля storage."""
    module = dataclasses.replace(
        storage_module,
        lifespan=storage_lifespan(storage_config=bucket, limits=LIMITS),
    )
    async with app_client([module], lifespan=True) as http:
        yield http


async def ask_url(
    client: AsyncClient,
    *,
    name: str = "report.png",
    content_type: str = PNG,
    size: int = 4,
) -> dict[str, Any]:
    """Запросить ссылку на загрузку и вернуть ответ ручки."""
    response = await client.post(
        "/files/upload-url",
        json={"original_name": name, "content_type": content_type, "size": size},
    )
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


async def put_object(url: str, payload: bytes, content_type: str = PNG) -> str:
    """Залить объект по подписанной ссылке и вернуть его ETag."""
    async with httpx.AsyncClient() as http:
        response = await http.put(url, content=payload, headers={"content-type": content_type})
    assert response.status_code == 200, response.text
    return response.headers["etag"].strip('"')


async def uploaded(
    client: AsyncClient,
    payload: bytes = b"data",
    *,
    declared: int | None = None,
    content_type: str = PNG,
) -> tuple[UUID, str]:
    """Пройти первую фазу: получить ссылку и залить объект."""
    ticket = await ask_url(
        client,
        content_type=content_type,
        size=len(payload) if declared is None else declared,
    )
    etag = await put_object(ticket["upload_url"], payload, ticket["content_type"])
    return UUID(ticket["file_id"]), etag


async def confirmed(client: AsyncClient, payload: bytes = b"data") -> UUID:
    """Пройти обе фазы и вернуть идентификатор готового файла."""
    file_id, etag = await uploaded(client, payload)
    response = await client.post(f"/files/{file_id}/confirm", json={"etag": etag})
    assert response.status_code == 200, response.text
    return file_id


async def row_of(file_id: UUID) -> File | None:
    """Строка файла из базы или None."""
    async with session_module.session_factory() as session:
        return await session.get(File, file_id)


async def stored(file_id: UUID) -> File:
    """Строка файла, которая обязана существовать."""
    file = await row_of(file_id)
    assert file is not None
    return file


async def count_files() -> int:
    """Сколько всего строк в таблице файлов."""
    async with session_module.session_factory() as session:
        return (await session.scalars(select(func.count()).select_from(File))).one()


async def outbox_topics() -> list[str]:
    """Топики событий, накопленных в outbox."""
    async with session_module.session_factory() as session:
        return list((await session.scalars(select(OutboxMessage.topic))).all())


async def age(file_id: UUID, *, seconds: int) -> None:
    """Состарить строку: сдвинуть `created_at` в прошлое."""
    moment = datetime.now(tz=UTC) - timedelta(seconds=seconds)
    async with session_module.session_factory() as session, session.begin():
        await session.execute(update(File).where(File.id == file_id).values(created_at=moment))


async def test_upload_url_creates_a_pending_row_and_signs_the_key(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    ticket = await ask_url(client, name="отчёт.png", size=4)

    file = await stored(UUID(ticket["file_id"]))
    assert (file.status, file.etag, file.owner_id) == (FileStatus.PENDING, None, None)
    assert (file.bucket, file.original_name, file.size) == (bucket.bucket, "отчёт.png", 4)
    assert file.key.startswith("uploads/") and str(file.id) in file.key
    assert file.original_name not in file.key
    assert f"/{bucket.bucket}/{file.key}?" in ticket["upload_url"]
    assert "X-Amz-Signature" in ticket["upload_url"]
    assert (ticket["content_type"], ticket["expires_in"]) == (PNG, 900)


async def test_upload_url_rejects_a_forbidden_content_type(client: AsyncClient) -> None:
    """Отказ до создания строки: клиент не должен узнавать о запрете после заливки."""
    response = await client.post(
        "/files/upload-url",
        json={"original_name": "virus.exe", "content_type": "application/x-msdownload", "size": 10},
    )

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-failed")
    assert await count_files() == 0


async def test_upload_url_rejects_an_oversized_declaration(client: AsyncClient) -> None:
    response = await client.post(
        "/files/upload-url",
        json={"original_name": "big.png", "content_type": PNG, "size": LIMITS.max_file_size + 1},
    )

    assert response.status_code == 422
    assert await count_files() == 0


async def test_confirm_without_an_uploaded_object_is_404_and_keeps_the_row_pending(
    client: AsyncClient,
) -> None:
    """Критерий этапа: объекта нет — 404, строка ждёт своей загрузки дальше."""
    ticket = await ask_url(client)

    response = await client.post(
        f"/files/{ticket['file_id']}/confirm",
        json={"etag": "d41d8cd98f00b204e9800998ecf8427e"},
    )

    assert response.status_code == 404
    file = await stored(UUID(ticket["file_id"]))
    assert file.status is FileStatus.PENDING
    assert await outbox_topics() == []


async def test_confirm_of_an_oversized_object_is_422_and_removes_it_from_the_bucket(
    client: AsyncClient,
    files: FileStorage,
) -> None:
    """Критерий этапа: заявке о размере верить нельзя, проверяется факт."""
    file_id, etag = await uploaded(client, b"x" * (LIMITS.max_file_size + 1), declared=8)
    key = (await stored(file_id)).key

    response = await client.post(f"/files/{file_id}/confirm", json={"etag": etag})

    assert response.status_code == 422
    assert "exceeds the limit" in response.json()["reason"]
    assert await files.objects.head_object(key) is None
    assert (await stored(file_id)).status is FileStatus.PENDING


async def test_confirm_of_a_size_mismatch_is_422(client: AsyncClient, files: FileStorage) -> None:
    """Размер в пределах лимита, но не тот, что заявляли, — тоже отказ."""
    file_id, etag = await uploaded(client, b"x" * 100, declared=4)
    key = (await stored(file_id)).key

    response = await client.post(f"/files/{file_id}/confirm", json={"etag": etag})

    assert response.status_code == 422
    assert "differs from the declared" in response.json()["reason"]
    assert await files.objects.head_object(key) is None


async def test_confirm_of_an_object_with_another_content_type_is_422(
    client: AsyncClient,
    files: FileStorage,
) -> None:
    """Тип вшит в подпись, поэтому чужой тип означает объект, положенный мимо ссылки."""
    ticket = await ask_url(client, size=4)
    file = await stored(UUID(ticket["file_id"]))
    put = await files.objects.client.put_object(
        Bucket=file.bucket,
        Key=file.key,
        Body=b"data",
        ContentType="text/plain",
    )

    response = await client.post(
        f"/files/{file.id}/confirm",
        json={"etag": put["ETag"].strip('"')},
    )

    assert response.status_code == 422
    assert "content type" in response.json()["reason"]
    assert await files.objects.head_object(file.key) is None


async def test_confirm_with_a_wrong_etag_is_422(client: AsyncClient, files: FileStorage) -> None:
    file_id, _ = await uploaded(client, b"data")
    key = (await stored(file_id)).key

    response = await client.post(
        f"/files/{file_id}/confirm",
        json={"etag": "0" * 32},
    )

    assert response.status_code == 422
    assert "etag" in response.json()["reason"]
    assert await files.objects.head_object(key) is None


async def test_confirm_marks_the_file_ready_and_emits_the_event(client: AsyncClient) -> None:
    file_id, etag = await uploaded(client, b"payload")

    response = await client.post(f"/files/{file_id}/confirm", json={"etag": etag})

    file = await stored(file_id)
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert (file.status, file.etag) == (FileStatus.READY, etag)
    assert await outbox_topics() == ["file.confirmed"]


async def test_confirmation_and_the_event_share_one_transaction(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Критерий этапа: откат уносит и смену статуса, и событие.

    Транзакция роняется после того, как её UPDATE и INSERT уже ушли в базу, —
    иначе тест доказывал бы только то, что до записи дело не дошло.
    """
    file_id, etag = await uploaded(client, b"payload")

    with failing_commit(), pytest.raises(RuntimeError, match="commit refused"):
        await confirm_upload(
            file_id,
            ConfirmRequest(etag=etag),
            session_factory=sessions,
            storage=files,
        )

    assert (await stored(file_id)).status is FileStatus.PENDING
    assert await outbox_topics() == []


async def test_confirm_is_idempotent(client: AsyncClient, files: FileStorage) -> None:
    """Ретрай клиента после обрыва не должен ни падать, ни дублировать событие.

    Второй раз объект не перепроверяется: ретрай с неудачным ETag удалил бы
    содержимое уже принятого файла.
    """
    file_id, etag = await uploaded(client, b"payload")
    key = (await stored(file_id)).key

    first = await client.post(f"/files/{file_id}/confirm", json={"etag": etag})
    second = await client.post(f"/files/{file_id}/confirm", json={"etag": etag})
    third = await client.post(f"/files/{file_id}/confirm", json={"etag": "0" * 32})

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 200)
    assert second.json()["status"] == "ready"
    assert await outbox_topics() == ["file.confirmed"]
    assert await files.objects.head_object(key) is not None


async def test_a_confirm_that_lost_the_race_emits_no_second_event(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Соседний запрос успел подтвердить файл, пока мы ходили в хранилище.

    Состояние перечитывается в пишущей транзакции именно ради этого: без
    повторной проверки проигравший гонку запрос выписал бы второе событие об
    одном и том же файле.
    """
    file_id, etag = await uploaded(client, b"payload")
    original: Callable[..., Any] = ObjectStorage.head_object
    raced = False

    async def confirm_meanwhile(
        self: ObjectStorage,
        key: str,
        *,
        bucket: str | None = None,
    ) -> Any:
        nonlocal raced
        info = await original(self, key, bucket=bucket)
        if not raced:
            raced = True
            await confirm_upload(
                file_id,
                ConfirmRequest(etag=etag),
                session_factory=sessions,
                storage=files,
            )
        return info

    monkeypatch.setattr(ObjectStorage, "head_object", confirm_meanwhile)
    file = await confirm_upload(
        file_id,
        ConfirmRequest(etag=etag),
        session_factory=sessions,
        storage=files,
    )

    assert file.status is FileStatus.READY
    assert await outbox_topics() == ["file.confirmed"]


async def test_get_returns_metadata_and_a_working_download_link(client: AsyncClient) -> None:
    file_id = await confirmed(client, b"payload")

    response = await client.get(f"/files/{file_id}")

    payload = response.json()
    assert response.status_code == 200
    assert payload["original_name"] == "report.png"
    async with httpx.AsyncClient() as http:
        downloaded = await http.get(payload["download_url"])
    assert downloaded.content == b"payload"
    assert "report.png" in downloaded.headers["content-disposition"]


async def test_a_pending_file_has_no_download_link(client: AsyncClient) -> None:
    """Объекта может ещё не быть: ссылка вела бы в никуда."""
    ticket = await ask_url(client)

    response = await client.get(f"/files/{ticket['file_id']}")

    assert response.status_code == 200
    assert response.json()["download_url"] is None


async def test_unknown_file_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/files/{uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_delete_hides_the_file_but_keeps_the_object(
    client: AsyncClient,
    files: FileStorage,
) -> None:
    file_id = await confirmed(client)
    key = (await stored(file_id)).key

    deleted = await client.delete(f"/files/{file_id}")

    assert deleted.status_code == 204
    assert not deleted.content
    assert (await stored(file_id)).status is FileStatus.DELETING
    # Объект ещё на месте: его уберёт задача, а не запрос.
    assert await files.objects.head_object(key) is not None
    assert (await client.get(f"/files/{file_id}")).status_code == 404
    assert (await client.post(f"/files/{file_id}/confirm", json={"etag": "x"})).status_code == 404


async def test_delete_is_idempotent(client: AsyncClient) -> None:
    file_id = await confirmed(client)

    first = await client.delete(f"/files/{file_id}")
    second = await client.delete(f"/files/{file_id}")

    assert (first.status_code, second.status_code) == (204, 204)


async def test_the_deletion_task_removes_the_object_and_the_row(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    file_id = await confirmed(client)
    key = (await stored(file_id)).key
    await client.delete(f"/files/{file_id}")

    purged = await delete_marked(session_factory=sessions, storage=files)

    assert purged == 1
    assert await files.objects.head_object(key) is None
    assert await row_of(file_id) is None


async def test_a_failing_object_delete_keeps_the_row_and_the_rest_of_the_batch(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Один проблемный файл не должен ни ронять проход, ни терять строку."""
    broken = await confirmed(client, b"broken")
    healthy = await confirmed(client, b"healthy")
    broken_key = (await stored(broken)).key
    for file_id in (broken, healthy):
        await client.delete(f"/files/{file_id}")

    original: Callable[..., Any] = ObjectStorage.delete_object

    async def flaky(
        self: ObjectStorage,
        key: str,
        *,
        bucket: str | None = None,
    ) -> None:
        if key == broken_key:
            raise ConnectionError("storage is unreachable")
        await original(self, key, bucket=bucket)

    monkeypatch.setattr(ObjectStorage, "delete_object", flaky)
    purged = await delete_marked(session_factory=sessions, storage=files)

    assert purged == 1
    assert await row_of(healthy) is None
    # Строка осталась: без неё ключ объекта был бы потерян навсегда.
    assert (await stored(broken)).status is FileStatus.DELETING
    assert await files.objects.head_object(broken_key) is not None


async def test_the_orphan_sweeper_removes_the_row_and_the_object(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Критерий этапа: клиент пропал после получения ссылки."""
    file_id, _ = await uploaded(client, b"abandoned")
    key = (await stored(file_id)).key
    await age(file_id, seconds=LIMITS.orphan_ttl + 60)

    purged = await sweep_orphans(session_factory=sessions, storage=files)

    assert purged == 1
    assert await row_of(file_id) is None
    assert await files.objects.head_object(key) is None


async def test_the_orphan_sweeper_spares_fresh_uploads(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Пока ссылка жива, клиент вправе долить файл."""
    file_id, _ = await uploaded(client, b"fresh")

    purged = await sweep_orphans(session_factory=sessions, storage=files)

    assert purged == 0
    assert (await stored(file_id)).status is FileStatus.PENDING


async def test_the_orphan_sweeper_ignores_confirmed_files(
    client: AsyncClient,
    files: FileStorage,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    file_id = await confirmed(client)
    await age(file_id, seconds=LIMITS.orphan_ttl + 60)

    assert await sweep_orphans(session_factory=sessions, storage=files) == 0
    assert (await stored(file_id)).status is FileStatus.READY


async def test_the_sweep_task_builds_its_own_client_and_settings(
    client: AsyncClient,
    bucket: S3Settings,
    files: FileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Задача в воркере поднимает клиент сама: lifespan модуля туда не доходит."""
    monkeypatch.setattr(storage_tasks, "s3_settings", bucket)
    monkeypatch.setattr(storage_tasks, "storage_settings", LIMITS)
    file_id, _ = await uploaded(client, b"abandoned")
    key = (await stored(file_id)).key
    await age(file_id, seconds=LIMITS.orphan_ttl + 60)

    assert await storage_tasks.sweep_orphaned_uploads() == 1
    assert await row_of(file_id) is None
    assert await files.objects.head_object(key) is None


async def test_the_deletion_task_builds_its_own_client_and_settings(
    client: AsyncClient,
    bucket: S3Settings,
    files: FileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage_tasks, "s3_settings", bucket)
    monkeypatch.setattr(storage_tasks, "storage_settings", LIMITS)
    file_id = await confirmed(client)
    key = (await stored(file_id)).key
    await client.delete(f"/files/{file_id}")

    assert await storage_tasks.delete_marked_files() == 1
    assert await row_of(file_id) is None
    assert await files.objects.head_object(key) is None


async def test_list_is_keyset_paginated_and_hides_deleted_files(client: AsyncClient) -> None:
    first = await confirmed(client, b"one")
    second = await confirmed(client, b"two")
    third = await confirmed(client, b"three")
    await client.delete(f"/files/{second}")

    page = (await client.get("/files", params={"limit": 1})).json()
    rest = (await client.get("/files", params={"limit": 10, "cursor": page["next_cursor"]})).json()

    assert [item["id"] for item in page["items"]] == [str(third)]
    assert [item["id"] for item in rest["items"]] == [str(first)]
    assert rest["next_cursor"] is None


async def test_list_rejects_a_malformed_cursor(client: AsyncClient) -> None:
    response = await client.get("/files", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-failed")


async def test_list_returns_orm_rows_usable_after_the_session_closed(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Сервис отдаёт отсоединённые объекты: обращение к ним не должно лезть в БД."""
    await confirmed(client)

    page = await list_files(PageParams(limit=10), session_factory=sessions)

    assert [item.status for item in page.items] == [FileStatus.READY]


async def test_s3_calls_never_happen_inside_a_transaction(
    client: AsyncClient,
    files: FileStorage,
    guard_transactions: TransactionWatch,
) -> None:
    """Критерий этапа: полный цикл под сторожем, и сам сторож не вхолостую."""
    file_id = await confirmed(client, b"payload")
    assert (await client.get(f"/files/{file_id}")).status_code == 200
    assert (await client.delete(f"/files/{file_id}")).status_code == 204
    assert guard_transactions.sessions, "guard saw no transactions at all"

    async with session_module.session_factory() as session, session.begin():
        await session.execute(text("SELECT 1"))
        with pytest.raises(AssertionError, match="transaction was open"):
            await files.objects.head_object("uploads/whatever")


def test_storage_is_registered_in_the_application() -> None:
    """Модуль подключён к боевому приложению, а не только к тестовому."""
    paths = set(create_app().openapi()["paths"])

    assert {"/files", "/files/upload-url", "/files/{file_id}", "/files/{file_id}/confirm"} <= paths
    assert storage_module in MODULES


def test_models_are_declared_for_alembic() -> None:
    """Без пакета моделей в манифесте alembic не увидит таблицу."""
    assert storage_module.models == "app.modules.storage.models"
    assert File.__tablename__ in File.metadata.tables


def test_periodic_tasks_are_declared_with_schedules() -> None:
    schedules = {
        task_name(storage_module, task): getattr(task, SCHEDULE_ATTR, None)
        for task in storage_module.tasks
    }

    assert set(schedules) == {
        "storage.sweep_orphaned_uploads",
        "storage.delete_marked_files",
        "storage.cleanup_file_upload_staging",
    }
    assert all(declared for declared in schedules.values())


def test_settings_match_the_env_example() -> None:
    settings = StorageSettings()

    assert settings.max_file_size == 26_214_400
    assert settings.orphan_ttl == 3600
    assert settings.deletion_interval == 60
    assert "application/pdf" in settings.allowed_content_types


def test_allowed_types_are_read_as_a_comma_separated_list() -> None:
    """В .env список пишется через запятую, а не JSON-массивом."""
    settings = StorageSettings(allowed_content_types="image/png, Image/JPEG")

    assert settings.allowed_content_types == frozenset({"image/png", "image/jpeg"})
