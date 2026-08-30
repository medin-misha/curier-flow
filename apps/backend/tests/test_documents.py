"""DOCX-шаблоны: parser, API, S3-границы и жизненный цикл File."""

import dataclasses
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from http import HTTPStatus
from io import BytesIO
from typing import Any, Final, cast
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from lxml import etree
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.kernel.db import session as session_module
from app.kernel.errors import Conflict
from app.kernel.idempotency import is_idempotent
from app.kernel.security.authentication import is_authenticated
from app.kernel.security.tokens import issue_tokens, jwt_settings
from app.modules.documents.docx import (
    DocxLimits,
    DocxTemplateError,
    extract_template_fields,
    render_template,
)
from app.modules.documents.models import DocumentTemplate
from app.modules.documents.module import documents_lifespan, documents_module
from app.modules.documents.services import (
    DOCX_CONTENT_TYPE,
    DocumentsSettings,
)
from app.modules.storage.services import mark_for_deletion
from app.platform.files import File, FileStatus, file_policy
from app.platform.s3 import ObjectStorage, S3Settings, storage
from tests.asgi import app_client, build_app

ADMIN_ID: Final = UUID(int=601)
LIMITS: Final = DocxLimits(
    max_uncompressed_size=1024 * 1024,
    max_archive_entries=100,
    max_fields=20,
)
SETTINGS: Final = DocumentsSettings(
    max_uncompressed_size=LIMITS.max_uncompressed_size,
    max_archive_entries=LIMITS.max_archive_entries,
    max_fields=LIMITS.max_fields,
    max_value_length=100,
)
PROBLEM_JSON: Final = "application/problem+json"
_WORD_NAMESPACE: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOCX_MAIN_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)


@dataclass
class TransactionWatch:
    """SQLAlchemy-сессии, открывавшие транзакции в текущем тесте."""

    sessions: list[Session] = field(default_factory=list)

    def open_now(self) -> list[Session]:
        """Вернуть сессии с ещё открытой транзакцией."""
        return [session for session in self.sessions if session.in_transaction()]


def guarded(method: Any, watch: TransactionWatch) -> Any:
    """Запретить bounded S3 read при открытой DB-транзакции."""

    async def call(self: ObjectStorage, *args: Any, **kwargs: Any) -> Any:
        assert not watch.open_now(), "ObjectStorage.read_object ran inside a DB transaction"
        return await method(self, *args, **kwargs)

    return call


@pytest.fixture(autouse=True)
def guard_transactions(monkeypatch: pytest.MonkeyPatch) -> Iterator[TransactionWatch]:
    """Сторожить порядок DB close → S3."""
    watch = TransactionWatch()

    def track(session: Session, _transaction: Any, _connection: Any) -> None:
        watch.sessions.append(session)

    event.listen(Session, "after_begin", track)
    monkeypatch.setattr(ObjectStorage, "read_object", guarded(ObjectStorage.read_object, watch))
    yield watch
    event.remove(Session, "after_begin", track)


@pytest.fixture
async def bucket(minio_endpoint: str) -> AsyncIterator[S3Settings]:
    """Отдельный MinIO bucket на тест."""
    config = S3Settings(endpoint_url=minio_endpoint, bucket=f"documents-{uuid4().hex[:8]}")
    async with storage(config) as objects:
        await objects.client.create_bucket(Bucket=config.bucket)
    yield config


@pytest.fixture
async def documents_database(clean_db: None) -> AsyncIterator[None]:  # noqa: ARG001
    """Удалять шаблоны до общей очистки File следующего теста."""
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(DocumentTemplate))
    try:
        yield
    finally:
        async with session_module.session_factory() as session, session.begin():
            await session.execute(delete(DocumentTemplate))


@pytest.fixture
async def client(
    bucket: S3Settings,
    documents_database: None,  # noqa: ARG001
) -> AsyncIterator[AsyncClient]:
    """Клиент documents с настоящими PostgreSQL, MinIO и Admin JWT."""
    module = dataclasses.replace(
        documents_module,
        lifespan=documents_lifespan(storage_config=bucket, settings=SETTINGS),
    )
    async with app_client([module], lifespan=True, raise_app_exceptions=False) as http:
        access = issue_tokens(
            ADMIN_ID,
            settings=jwt_settings,
            claims={"kind": "admin"},
        ).access_token
        http.headers["authorization"] = f"Bearer {access}"
        yield http


def make_docx(
    paragraphs: list[list[str]],
    *,
    header: list[list[str]] | None = None,
) -> bytes:
    """Собрать минимальный OOXML package с заданными Word runs."""
    output = BytesIO()
    overrides = [f'<Override PartName="/word/document.xml" ContentType="{_DOCX_MAIN_TYPE}"/>']
    if header is not None:
        overrides.append(
            '<Override PartName="/word/header1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.header+xml"/>'
        )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{''.join(overrides)}"
        "</Types>"
    )
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", word_xml("document", paragraphs))
        if header is not None:
            archive.writestr("word/header1.xml", word_xml("hdr", header))
    return output.getvalue()


def word_xml(root_name: str, paragraphs: list[list[str]]) -> str:
    """Собрать Word XML, экранируя текст каждого run через lxml."""
    root = etree.Element(f"{{{_WORD_NAMESPACE}}}{root_name}", nsmap={"w": _WORD_NAMESPACE})
    parent = (
        etree.SubElement(root, f"{{{_WORD_NAMESPACE}}}body") if root_name == "document" else root
    )
    for runs in paragraphs:
        paragraph = etree.SubElement(parent, f"{{{_WORD_NAMESPACE}}}p")
        for value in runs:
            run = etree.SubElement(paragraph, f"{{{_WORD_NAMESPACE}}}r")
            text = etree.SubElement(run, f"{{{_WORD_NAMESPACE}}}t")
            text.text = value
    return etree.tostring(root, encoding="unicode", xml_declaration=False)


def text_of(docx: bytes, part: str = "word/document.xml") -> str:
    """Прочитать объединённый Word text из результата."""
    with ZipFile(BytesIO(docx)) as archive:
        root = etree.fromstring(archive.read(part))
    return "".join(cast(Iterator[str], root.itertext()))


async def create_source(
    bucket: S3Settings,
    body: bytes,
    *,
    name: str = "contract.docx",
    content_type: str = DOCX_CONTENT_TYPE,
    status: FileStatus = FileStatus.READY,
) -> UUID:
    """Положить объект в MinIO и согласованную строку File в PostgreSQL."""
    file_id = uuid4()
    key = f"templates/{file_id}"
    async with storage(bucket) as objects:
        uploaded = await objects.client.put_object(
            Bucket=bucket.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    etag = str(uploaded["ETag"]).strip('"')
    async with session_module.session_factory() as session, session.begin():
        session.add(
            File(
                id=file_id,
                bucket=bucket.bucket,
                key=key,
                original_name=name,
                content_type=content_type,
                size=len(body),
                etag=etag if status is FileStatus.READY else None,
                status=status,
                owner_id=ADMIN_ID,
            )
        )
    return file_id


async def create_template(
    client: AsyncClient,
    bucket: S3Settings,
    *,
    name: str = "Courier contract",
    body: bytes | None = None,
) -> dict[str, Any]:
    """Создать исходный File и шаблон через публичный API."""
    source = body or make_docx(
        [["Courier: ", "{courier.", "full_name}", ", price {transport.price}"]],
        header=[["Number {courier.number}"]],
    )
    file_id = await create_source(bucket, source)
    response = await client.post(
        "/document-templates",
        json={"name": name, "file_id": str(file_id)},
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    payload: dict[str, Any] = response.json()
    return payload


def test_docx_engine_handles_split_runs_headers_and_escaping() -> None:
    source = make_docx(
        [["Courier ", "{courier.", "full_name}", " pays {transport.price}"]],
        header=[["No. {courier.number}"]],
    )

    fields = extract_template_fields(source, limits=LIMITS)
    rendered = render_template(
        source,
        {
            "courier.full_name": "A & B <Company>",
            "courier.number": "42",
            "transport.price": "3 500 CZK",
        },
        limits=LIMITS,
    )

    assert fields == {
        "courier": ["full_name", "number"],
        "transport": ["price"],
    }
    assert text_of(rendered) == "Courier A & B <Company> pays 3 500 CZK"
    assert text_of(rendered, "word/header1.xml") == "No. 42"


@pytest.mark.parametrize(
    "source",
    [
        b"not a zip",
        make_docx([["No fields"]]),
        make_docx([["Bad {Courier.full-name}"]]),
    ],
)
def test_docx_engine_rejects_invalid_templates(source: bytes) -> None:
    with pytest.raises(DocxTemplateError):
        extract_template_fields(source, limits=LIMITS)


def test_docx_engine_rejects_unsafe_archive_paths() -> None:
    source = BytesIO()
    with ZipFile(source, "w") as archive:
        archive.writestr("../word/document.xml", "unsafe")

    with pytest.raises(DocxTemplateError, match="unsafe or duplicate path"):
        extract_template_fields(source.getvalue(), limits=LIMITS)


def test_documents_settings_match_the_env_example() -> None:
    assert DocumentsSettings().model_dump() == {
        "max_uncompressed_size": 104_857_600,
        "max_archive_entries": 2048,
        "max_fields": 200,
        "max_value_length": 10_000,
    }
    assert DOCX_CONTENT_TYPE in file_policy.allowed_content_types


def test_route_markers_are_explicit() -> None:
    app = build_app([documents_module])
    assert documents_module.router is not None
    document_routes = [
        route for route in documents_module.router.routes if isinstance(route, APIRoute)
    ]

    assert len(document_routes) == 5
    assert all(is_authenticated(route.endpoint) for route in document_routes)
    assert not any(is_idempotent(route.endpoint) for route in document_routes)
    assert "/document-templates" in app.openapi()["paths"]


async def test_every_endpoint_requires_admin_jwt(client: AsyncClient) -> None:
    authorization = client.headers.pop("authorization")
    template_id = uuid4()
    requests = (
        ("POST", "/document-templates"),
        ("GET", "/document-templates"),
        ("GET", f"/document-templates/{template_id}"),
        ("POST", f"/document-templates/{template_id}/render"),
        ("DELETE", f"/document-templates/{template_id}"),
    )
    try:
        for method, path in requests:
            response = await client.request(method, path, json={})
            assert response.status_code == HTTPStatus.UNAUTHORIZED, (method, path, response.text)
            assert response.headers["content-type"] == PROBLEM_JSON
            assert response.json()["reason"] == "missing-token"
    finally:
        client.headers["authorization"] = authorization


async def test_create_extracts_fields_and_exact_retry_is_natural_key(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    file_id = await create_source(
        bucket,
        make_docx([["{transport.color} {courier.name} {courier.name}"]]),
    )
    body = {"name": "Rental agreement", "file_id": str(file_id)}

    created = await client.post("/document-templates", json=body)
    repeated = await client.post("/document-templates", json=body)
    conflict = await client.post(
        "/document-templates",
        json={**body, "name": "Another agreement"},
    )

    assert created.status_code == HTTPStatus.CREATED
    assert repeated.status_code == HTTPStatus.OK
    assert repeated.json() == created.json()
    assert created.json()["fields"] == {"courier": ["name"], "transport": ["color"]}
    assert conflict.status_code == HTTPStatus.CONFLICT
    assert conflict.json()["reason"] == "template-file-in-use"


async def test_render_returns_docx_without_creating_a_file(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    template = await create_template(client, bucket)
    async with session_module.session_factory() as session:
        before = await session.scalar(select(func.count()).select_from(File))

    response = await client.post(
        f"/document-templates/{template['id']}/render",
        json={
            "values": {
                "courier": {"full_name": "Jan & Eva", "number": "C-42"},
                "transport": {"price": "3 500 CZK"},
            }
        },
    )
    async with session_module.session_factory() as session:
        after = await session.scalar(select(func.count()).select_from(File))

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == DOCX_CONTENT_TYPE
    assert response.headers["cache-control"] == "no-store"
    assert "filename*=UTF-8''Courier%20contract.docx" in response.headers["content-disposition"]
    assert text_of(response.content) == "Courier: Jan & Eva, price 3 500 CZK"
    assert text_of(response.content, "word/header1.xml") == "Number C-42"
    assert before == after == 1


async def test_render_rejects_missing_extra_non_string_and_multiline_values(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    template = await create_template(client, bucket)
    path = f"/document-templates/{template['id']}/render"

    mismatch = await client.post(
        path,
        json={"values": {"courier": {"full_name": "Jan", "number": "1", "extra": "x"}}},
    )
    non_string = await client.post(
        path,
        json={
            "values": {
                "courier": {"full_name": 12, "number": "1"},
                "transport": {"price": "10"},
            }
        },
    )
    multiline = await client.post(
        path,
        json={
            "values": {
                "courier": {"full_name": "Jan\nNovak", "number": "1"},
                "transport": {"price": "10"},
            }
        },
    )

    assert mismatch.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert mismatch.json()["reason"] == "field-mismatch"
    assert mismatch.json()["missing_fields"] == ["transport.price"]
    assert mismatch.json()["unexpected_fields"] == ["courier.extra"]
    assert non_string.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert multiline.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert multiline.json()["reason"] == "invalid-field-values"


async def test_create_rejects_non_docx_and_invalid_docx(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    pdf = await create_source(
        bucket,
        b"pdf",
        name="contract.docx",
        content_type="application/pdf",
    )
    broken = await create_source(bucket, b"not a docx")

    wrong_type = await client.post(
        "/document-templates",
        json={"name": "PDF", "file_id": str(pdf)},
    )
    invalid = await client.post(
        "/document-templates",
        json={"name": "Broken", "file_id": str(broken)},
    )

    assert wrong_type.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert wrong_type.json()["reason"] == "invalid-template-type"
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid.json()["reason"] == "invalid-docx-template"


async def test_list_detail_delete_and_file_protection(
    client: AsyncClient,
    bucket: S3Settings,
) -> None:
    first = await create_template(client, bucket, name="First")
    await create_template(client, bucket, name="Second")
    await create_template(client, bucket, name="Third")

    page = (await client.get("/document-templates", params={"limit": 2})).json()
    rest = (await client.get("/document-templates", params={"cursor": page["next_cursor"]})).json()
    detail = await client.get(f"/document-templates/{first['id']}")

    with pytest.raises(Conflict) as protected:
        await mark_for_deletion(
            UUID(first["file_id"]),
            session_factory=session_module.session_factory,
        )
    deleted = await client.delete(f"/document-templates/{first['id']}")
    await mark_for_deletion(
        UUID(first["file_id"]),
        session_factory=session_module.session_factory,
    )

    assert len(page["items"]) == 2
    assert page["next_cursor"] is not None
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None
    assert detail.status_code == HTTPStatus.OK
    assert detail.json() == first
    assert protected.value.extra["reason"] == "file-in-use"
    assert deleted.status_code == HTTPStatus.NO_CONTENT
    assert not deleted.content
    assert (await client.get(f"/document-templates/{first['id']}")).status_code == 404


async def test_database_requires_ready_file_and_has_keyset_schema(
    bucket: S3Settings,
    documents_database: None,  # noqa: ARG001
) -> None:
    pending_file = await create_source(
        bucket,
        make_docx([["{courier.name}"]]),
        status=FileStatus.PENDING,
    )

    with pytest.raises(IntegrityError):
        async with session_module.session_factory() as session, session.begin():
            session.add(
                DocumentTemplate(
                    name="Pending source",
                    file_id=pending_file,
                    fields={"courier": ["name"]},
                )
            )

    async with session_module.session_factory() as session:
        constraints = set(
            await session.scalars(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'document_templates'::regclass"
                )
            )
        )
        triggers = set(
            await session.scalars(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE NOT tgisinternal AND "
                    "tgrelid IN ('document_templates'::regclass, 'files'::regclass)"
                )
            )
        )
        index_definition = await session.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'document_templates' "
                "AND indexname = 'ix_document_templates_keyset'"
            )
        )

    assert {
        "ck_document_templates_fields_object",
        "ck_document_templates_name_trimmed",
        "fk_document_templates_file_id_files",
        "uq_document_templates_file_id",
    } <= constraints
    assert {
        "documents_protect_template_file",
        "documents_require_ready_template_file",
    } <= triggers
    assert index_definition is not None
    assert "created_at DESC, id DESC" in index_definition


async def test_s3_read_never_runs_inside_a_transaction(
    bucket: S3Settings,
    documents_database: None,  # noqa: ARG001
    guard_transactions: TransactionWatch,
) -> None:
    """Доказать, что guard действительно падает при нарушении."""
    async with (
        storage(bucket) as objects,
        session_module.session_factory() as session,
        session.begin(),
    ):
        await session.execute(select(1))
        with pytest.raises(AssertionError, match="inside a DB transaction"):
            await objects.read_object("missing", max_size=1)
    assert guard_transactions.sessions
