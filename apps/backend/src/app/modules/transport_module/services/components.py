"""CRUD текущей комплектации транспорта."""

from typing import cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.crud import CRUD
from app.kernel.pagination import Page, PageParams
from app.modules.transport_module.models import TransportComponent
from app.modules.transport_module.schemas.requests import (
    TransportComponentCreate,
    TransportComponentPatch,
)
from app.modules.transport_module.services.common import normalize_trimmed, raise_known_integrity
from app.modules.transport_module.services.queries import (
    get_component,
    lock_transport,
    require_transport,
)


async def create_component(
    transport_id: UUID,
    request: TransportComponentCreate,
    *,
    session: AsyncSession,
) -> TransportComponent:
    """Добавить уникальную позицию в комплектацию существующего транспорта."""
    await lock_transport(transport_id, session=session)
    normalized = request.model_copy(
        update={"name": normalize_trimmed(request.name, field="component-name", maximum=128)}
    )
    try:
        return await CRUD.create(TransportComponent, normalized, session, transport_id=transport_id)
    except IntegrityError as error:
        raise_known_integrity(error)


async def list_components(
    transport_id: UUID,
    page: PageParams,
    *,
    session: AsyncSession,
) -> Page[TransportComponent]:
    """Вернуть parent-scoped keyset-страницу комплектации."""
    await require_transport(transport_id, session=session)
    return await CRUD.list_page(
        TransportComponent,
        session,
        page=page,
        where=(TransportComponent.transport_id == transport_id,),
    )


async def patch_component(
    transport_id: UUID,
    component_id: UUID,
    patch: TransportComponentPatch,
    *,
    session: AsyncSession,
) -> TransportComponent:
    """Изменить только компонент из указанного parent path."""
    await lock_transport(transport_id, session=session)
    component = await get_component(transport_id, component_id, session=session, for_update=True)
    updates: dict[str, object] = {}
    if "name" in patch.model_fields_set:
        updates["name"] = normalize_trimmed(
            cast(str, patch.name),
            field="component-name",
            maximum=128,
        )
    normalized = patch.model_copy(update=updates)
    try:
        return await CRUD.update(component, normalized, session)
    except IntegrityError as error:
        raise_known_integrity(error)


async def delete_component(
    transport_id: UUID,
    component_id: UUID,
    *,
    session: AsyncSession,
) -> None:
    """Удалить компонент только внутри указанного транспорта."""
    await lock_transport(transport_id, session=session)
    component = await get_component(transport_id, component_id, session=session, for_update=True)
    await CRUD.delete(component, session)
