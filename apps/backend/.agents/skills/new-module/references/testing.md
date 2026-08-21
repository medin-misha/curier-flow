## Шаг 14. Тесты

`tests/test_<name>.py`. Заготовка ниже проверяет то, что ломается чаще всего:
ручка создаёт строку, событие уезжает в outbox той же транзакцией, список
листается курсором, PATCH меняет только присланное и не пропускает `null`,
DELETE отвечает 204, а повтор — 404.

```python
"""Модуль notes: создание, событие, список, PATCH и DELETE."""

from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.kernel.db import session as session_module
from app.kernel.events.models import OutboxMessage
from app.modules.notes.models import Note
from app.modules.notes.module import notes_module
from tests.asgi import app_client

NOTE = {"title": "first", "body": "hello"}


@pytest.fixture
async def client(clean_db: None) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    """Клиент к приложению из одного модуля notes на чистой базе.

    `clean_db`, а не `session`: тесту нужны настоящие транзакции — иначе
    «событие и данные закоммитились вместе» проверить нечем.

    Свою таблицу тест чистит сам: `clean_db` знает только про таблицы,
    перечисленные в `tests/conftest.py::TEST_MODELS`, а строки, оставленные
    соседним тестом, ломают счёт страниц в проверке пагинации.
    """
    async with session_module.session_factory() as session, session.begin():
        await session.execute(delete(Note))
    async with app_client([notes_module]) as http:
        yield http


async def test_creating_a_note_returns_it(client: AsyncClient) -> None:
    response = await client.post("/notes", json=NOTE)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["title"] == "first"


async def test_creating_a_note_writes_the_event_to_the_outbox(client: AsyncClient) -> None:
    await client.post("/notes", json=NOTE)

    async with session_module.session_factory() as session:
        topics = (await session.scalars(select(OutboxMessage.topic))).all()

    assert list(topics) == ["note.created"]


async def test_unknown_field_is_rejected(client: AsyncClient) -> None:
    """`BaseRequest` объявлен с extra="forbid": опечатка не должна молчать."""
    response = await client.post("/notes", json={**NOTE, "owner_id": "nobody"})

    # Именно UNPROCESSABLE_ENTITY: UNPROCESSABLE_CONTENT появился в 3.13, а
    # проект собирается на 3.12, и mypy это поймает.
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_the_list_is_paginated_by_cursor(client: AsyncClient) -> None:
    for number in range(3):
        await client.post("/notes", json={**NOTE, "title": f"note {number}"})

    first = (await client.get("/notes", params={"limit": 2})).json()
    rest = (await client.get("/notes", params={"cursor": first["next_cursor"]})).json()

    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None


async def test_patch_changes_only_the_fields_sent(client: AsyncClient) -> None:
    created = (await client.post("/notes", json=NOTE)).json()

    patched = (await client.patch(f"/notes/{created['id']}", json={"title": "second"})).json()

    assert patched["title"] == "second"
    assert patched["body"] == created["body"]
    assert patched["updated_at"] > created["updated_at"]


async def test_explicit_null_is_rejected(client: AsyncClient) -> None:
    """`{"title": null}` — 422, а не NULL в NOT NULL-колонке."""
    created = (await client.post("/notes", json=NOTE)).json()

    response = await client.patch(f"/notes/{created['id']}", json={"title": None})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_delete_removes_the_note_and_repeats_answer_404(client: AsyncClient) -> None:
    created = (await client.post("/notes", json=NOTE)).json()

    first = await client.delete(f"/notes/{created['id']}")
    repeat = await client.delete(f"/notes/{created['id']}")

    assert first.status_code == HTTPStatus.NO_CONTENT
    assert not first.content
    assert repeat.status_code == HTTPStatus.NOT_FOUND
    assert (await client.get(f"/notes/{created['id']}")).status_code == HTTPStatus.NOT_FOUND
```

Что учесть:

- фикстуры `clean_db`, `session`, `broker`, `minio_endpoint`, `redis_dsn` живут
  в `tests/conftest.py`; там же объяснено, чем режим `clean_db` (настоящие
  транзакции) отличается от `session` (вложенная с откатом);
- **`clean_db` не знает про таблицу нового модуля.** Он чистит только то, что
  перечислено в `TEST_MODELS`. Либо чисти свою таблицу в собственной фикстуре
  (как в заготовке выше — так правки не выходят за пределы модуля), либо
  добавь модель в `TEST_MODELS` (так сделано для `File` модуля `storage`).
  Не сделав ни того ни другого, получишь тест, который проходит в одиночку и
  падает в полном прогоне;
- приложение собирается через `tests/asgi.py::app_client` из **списка
  манифестов**, а не из глобального `MODULES`: тест модуля не должен зависеть
  от соседей. `lifespan=True` нужен, только если у модуля есть `lifespan`;
- в тестах `assert` разрешён, докстринги не обязательны, но неиспользуемый
  аргумент-фикстуру придётся пометить `# noqa: ARG001`;
- если модуль ходит во внешний сервис — скопируй сторож `guard_transactions` из
  `tests/test_storage.py`: он падает, когда клиент дёргают при открытой
  транзакции.
