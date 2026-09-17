"""Проекция контактов последнего арендатора транспорта.

Revision ID: 6e4399783be9
Revises: 2908b0614e30
Create Date: 2026-09-17 11:59:17.762292
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e4399783be9"
down_revision: str | Sequence[str] | None = "2908b0614e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transport_courier_profiles",
        sa.Column("courier_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "(is_deleted AND full_name IS NULL AND phone IS NULL) OR "
            "(NOT is_deleted AND full_name IS NOT NULL AND phone IS NOT NULL)",
            name=op.f("ck_transport_courier_profiles_profile_state"),
        ),
        sa.PrimaryKeyConstraint("courier_id", name=op.f("pk_transport_courier_profiles")),
    )
    op.create_index(
        "ix_courier_transports_latest_rental",
        "courier_transports",
        ["transport_id", sa.literal_column("started_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    # Снимок контактов и его версия согласованы с конкурентными изменениями курьеров.
    op.execute("LOCK TABLE couriers IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        "INSERT INTO transport_courier_profiles "
        "(courier_id, full_name, phone, source_updated_at, is_deleted) "
        "SELECT id, full_name, phone, clock_timestamp(), false FROM couriers"
    )


def downgrade() -> None:
    op.drop_index("ix_courier_transports_latest_rental", table_name="courier_transports")
    op.drop_table("transport_courier_profiles")
