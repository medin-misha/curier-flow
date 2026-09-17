"""Защищённые HTTP-ручки транспорта, комплектации и аренды."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.session import get_ro_session, get_uow
from app.kernel.idempotency import idempotent
from app.kernel.pagination import Page, PageParams
from app.kernel.security.authentication import authenticated
from app.modules.transport_module.schemas.requests import (
    CourierTransportClose,
    CourierTransportContractAttach,
    CourierTransportCreate,
    CourierTransportPaymentPatch,
    TransportComponentCreate,
    TransportComponentPatch,
    TransportCreate,
    TransportPatch,
)
from app.modules.transport_module.schemas.responses import (
    CourierTransportResponse,
    TransportComponentResponse,
    TransportDetailResponse,
    TransportListItemResponse,
)
from app.modules.transport_module.services import (
    attach_contract,
    close_rental,
    create_component,
    create_rental,
    create_transport,
    delete_component,
    delete_transport,
    get_component,
    get_rental,
    get_transport,
    list_components,
    list_rentals,
    list_transports,
    patch_component,
    patch_rental_payment,
    patch_transport,
)

Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
PageQuery = Annotated[PageParams, Depends()]

router = APIRouter(tags=["transport"])


class TransportFilters:
    """Фильтры списка транспорта, разбираемые FastAPI из query string."""

    def __init__(
        self,
        transport_type: Annotated[str | None, Query(alias="type", max_length=64)] = None,
        serial_number: Annotated[str | None, Query(max_length=64)] = None,
        courier_id: UUID | None = None,
        is_available: bool | None = None,
    ) -> None:
        self.transport_type = transport_type
        self.serial_number = serial_number
        self.courier_id = courier_id
        self.is_available = is_available


Filters = Annotated[TransportFilters, Depends()]


@router.post("", status_code=HTTPStatus.CREATED, summary="Create a transport")
@authenticated
@idempotent
async def create(body: TransportCreate, uow: Uow) -> TransportDetailResponse:
    return await create_transport(body, session=uow)


@router.get("", summary="List transports")
@authenticated
async def list_page(
    page: PageQuery,
    session: RoSession,
    filters: Filters,
) -> Page[TransportListItemResponse]:
    return await list_transports(
        page,
        session=session,
        transport_type=filters.transport_type,
        serial_number=filters.serial_number,
        courier_id=filters.courier_id,
        is_available=filters.is_available,
    )


@router.get("/{transport_id}", summary="Transport by id")
@authenticated
async def retrieve(transport_id: UUID, session: RoSession) -> TransportDetailResponse:
    return await get_transport(transport_id, session=session)


@router.patch("/{transport_id}", summary="Update a transport")
@authenticated
async def update(
    transport_id: UUID,
    body: TransportPatch,
    uow: Uow,
) -> TransportDetailResponse:
    return await patch_transport(transport_id, body, session=uow)


@router.delete(
    "/{transport_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a transport",
)
@authenticated
async def remove(transport_id: UUID, uow: Uow) -> None:
    await delete_transport(transport_id, session=uow)


@router.post(
    "/{transport_id}/components",
    status_code=HTTPStatus.CREATED,
    summary="Add a transport component",
)
@authenticated
@idempotent
async def add_component(
    transport_id: UUID,
    body: TransportComponentCreate,
    uow: Uow,
) -> TransportComponentResponse:
    return TransportComponentResponse.model_validate(
        await create_component(transport_id, body, session=uow)
    )


@router.get("/{transport_id}/components", summary="List transport components")
@authenticated
async def component_list(
    transport_id: UUID,
    page: PageQuery,
    session: RoSession,
) -> Page[TransportComponentResponse]:
    found = await list_components(transport_id, page, session=session)
    return Page[TransportComponentResponse](
        items=[TransportComponentResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get(
    "/{transport_id}/components/{component_id}",
    summary="Transport component by id",
)
@authenticated
async def component_detail(
    transport_id: UUID,
    component_id: UUID,
    session: RoSession,
) -> TransportComponentResponse:
    return TransportComponentResponse.model_validate(
        await get_component(transport_id, component_id, session=session)
    )


@router.patch(
    "/{transport_id}/components/{component_id}",
    summary="Update a transport component",
)
@authenticated
async def update_component(
    transport_id: UUID,
    component_id: UUID,
    body: TransportComponentPatch,
    uow: Uow,
) -> TransportComponentResponse:
    return TransportComponentResponse.model_validate(
        await patch_component(transport_id, component_id, body, session=uow)
    )


@router.delete(
    "/{transport_id}/components/{component_id}",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Delete a transport component",
)
@authenticated
async def remove_component(transport_id: UUID, component_id: UUID, uow: Uow) -> None:
    await delete_component(transport_id, component_id, session=uow)


@router.post(
    "/{transport_id}/rentals",
    status_code=HTTPStatus.CREATED,
    summary="Create a rental period",
)
@authenticated
@idempotent
async def add_rental(
    transport_id: UUID,
    body: CourierTransportCreate,
    uow: Uow,
) -> CourierTransportResponse:
    return CourierTransportResponse.model_validate(
        await create_rental(transport_id, body, session=uow)
    )


@router.get("/{transport_id}/rentals", summary="List rental history")
@authenticated
async def rental_list(
    transport_id: UUID,
    page: PageQuery,
    session: RoSession,
) -> Page[CourierTransportResponse]:
    found = await list_rentals(transport_id, page, session=session)
    return Page[CourierTransportResponse](
        items=[CourierTransportResponse.model_validate(item) for item in found.items],
        next_cursor=found.next_cursor,
    )


@router.get("/{transport_id}/rentals/{rental_id}", summary="Rental by id")
@authenticated
async def rental_detail(
    transport_id: UUID,
    rental_id: UUID,
    session: RoSession,
) -> CourierTransportResponse:
    return CourierTransportResponse.model_validate(
        await get_rental(transport_id, rental_id, session=session)
    )


@router.patch("/{transport_id}/rentals/{rental_id}", summary="Update rental payment type")
@authenticated
async def update_rental_payment(
    transport_id: UUID,
    rental_id: UUID,
    body: CourierTransportPaymentPatch,
    uow: Uow,
) -> CourierTransportResponse:
    return CourierTransportResponse.model_validate(
        await patch_rental_payment(transport_id, rental_id, body, session=uow)
    )


@router.post("/{transport_id}/rentals/{rental_id}/close", summary="Close a rental")
@authenticated
@idempotent
async def close(
    transport_id: UUID,
    rental_id: UUID,
    body: CourierTransportClose,
    uow: Uow,
) -> CourierTransportResponse:
    return CourierTransportResponse.model_validate(
        await close_rental(transport_id, rental_id, body, session=uow)
    )


@router.post(
    "/{transport_id}/rentals/{rental_id}/contract",
    summary="Attach a signed contract",
)
@authenticated
@idempotent
async def contract(
    transport_id: UUID,
    rental_id: UUID,
    body: CourierTransportContractAttach,
    uow: Uow,
) -> CourierTransportResponse:
    return CourierTransportResponse.model_validate(
        await attach_contract(transport_id, rental_id, body, session=uow)
    )
