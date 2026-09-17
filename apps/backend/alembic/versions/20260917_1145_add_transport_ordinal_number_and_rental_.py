"""Порядковый номер транспорта и тип оплаты аренды.

Revision ID: 2908b0614e30
Revises: e1e4e4319e3e
Create Date: 2026-09-17 11:45:08.514091
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2908b0614e30"
down_revision: str | Sequence[str] | None = "e1e4e4319e3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "courier_transports",
        sa.Column(
            "payment_type",
            sa.Enum(
                "monthly",
                "weekly",
                "weekly_in_arrears",
                name="rental_payment_type",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_courier_transports_payment_type_allowed"),
        "courier_transports",
        "payment_type IS NULL OR payment_type IN ('monthly', 'weekly', 'weekly_in_arrears')",
    )
    op.add_column("transports", sa.Column("ordinal_number", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_transports_ordinal_number_positive"),
        "transports",
        "ordinal_number IS NULL OR ordinal_number > 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_transports_ordinal_number_positive"), "transports", type_="check")
    op.drop_column("transports", "ordinal_number")
    op.drop_constraint(
        op.f("ck_courier_transports_payment_type_allowed"), "courier_transports", type_="check"
    )
    op.drop_column("courier_transports", "payment_type")
