"""Перенос исторических записей с natural-key правилами регистрации."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils.compat import uuid7

from app.kernel.errors import Conflict
from app.modules.courier_module.models import Courier, CourierPlatformAccount
from app.modules.courier_module.schemas.imports import (
    CourierImportBatch,
    CourierImportRecord,
    CourierImportResponse,
    CourierImportResult,
)
from app.modules.courier_module.services.couriers import _emit_profile_changed
from app.modules.courier_module.services.queries import find_identity_in_session


async def import_couriers(
    batch: CourierImportBatch, *, dry_run: bool, session: AsyncSession
) -> CourierImportResponse:
    if dry_run:
        results = await _preview(batch, session=session)
    else:
        results = []
        for record in batch.couriers:
            try:
                courier_id, created = await _import_record(record, session=session)
            except Conflict as error:
                results.append(
                    CourierImportResult(
                        source_row=record.source_row,
                        legacy_id=record.legacy_id,
                        outcome="conflict",
                        reason=str(error.extra["reason"]),
                    )
                )
            else:
                results.append(
                    CourierImportResult(
                        source_row=record.source_row,
                        legacy_id=record.legacy_id,
                        outcome="created" if created else "existing",
                        courier_id=courier_id,
                    )
                )
    return CourierImportResponse(
        dry_run=dry_run,
        created_count=sum(row.outcome == "created" for row in results),
        would_create_count=sum(row.outcome == "would_create" for row in results),
        existing_count=sum(row.outcome == "existing" for row in results),
        conflict_count=sum(row.outcome == "conflict" for row in results),
        results=results,
    )


async def _import_record(
    record: CourierImportRecord, *, session: AsyncSession
) -> tuple[UUID, bool]:
    request = record.courier
    existing = await find_identity_in_session(request.email, request.phone, session=session)
    if existing is not None:
        return existing.id, False

    now = datetime.now(tz=UTC)
    values = request.model_dump(exclude={"platform_accounts"})
    values.update(
        id=uuid7(), updated_at=now, consent_at=now if request.consent_to_processing else None
    )
    inserted_id = await session.scalar(
        insert(Courier).values(**values).on_conflict_do_nothing().returning(Courier.id)
    )
    if inserted_id is None:
        winner = await find_identity_in_session(request.email, request.phone, session=session)
        if winner is None:
            raise Conflict("Courier identity changed concurrently", reason="identity-conflict")
        return winner.id, False

    for account in request.platform_accounts:
        session.add(
            CourierPlatformAccount(
                courier_id=inserted_id,
                platform=account.platform,
                status=account.status,
                created_at=request.created_at,
                updated_at=now,
            )
        )
    # Исторический перенос синхронизирует профиль, но не создаёт новую заявку.
    await _emit_profile_changed(inserted_id, request.full_name, request.phone, session=session)
    await session.flush()
    return inserted_id, True


async def _preview(
    batch: CourierImportBatch, *, session: AsyncSession
) -> list[CourierImportResult]:
    identities = (
        await session.execute(
            select(Courier.id, Courier.email, Courier.phone).where(
                or_(
                    Courier.email.in_([record.courier.email for record in batch.couriers]),
                    Courier.phone.in_([record.courier.phone for record in batch.couriers]),
                )
            )
        )
    ).all()
    emails = {row.email: row.id for row in identities}
    phones = {row.phone: row.id for row in identities}
    persistent = {row.id for row in identities}
    results = []
    for record in batch.couriers:
        email_id = emails.get(record.courier.email)
        phone_id = phones.get(record.courier.phone)
        result = CourierImportResult(
            source_row=record.source_row, legacy_id=record.legacy_id, outcome="would_create"
        )
        if email_id is not None and phone_id is not None and email_id != phone_id:
            result.outcome = "conflict"
            result.reason = "identity-split"
        elif (existing_id := email_id or phone_id) is not None:
            result.outcome = "existing"
            result.courier_id = existing_id if existing_id in persistent else None
        else:
            simulated_id = uuid7()
            emails[record.courier.email] = simulated_id
            phones[record.courier.phone] = simulated_id
        results.append(result)
    return results
