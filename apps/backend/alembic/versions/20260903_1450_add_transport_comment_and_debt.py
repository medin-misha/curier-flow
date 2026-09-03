"""add transport comment and debt

Revision ID: e1e4e4319e3e
Revises: 8e6f2c9a1b4d
Create Date: 2026-09-03 14:50:19.128617
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1e4e4319e3e"
down_revision: str | Sequence[str] | None = "8e6f2c9a1b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transports", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column(
        "transports",
        sa.Column(
            "debt_amount",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )
    op.alter_column("transports", "debt_amount", server_default=None)
    op.create_check_constraint(
        op.f("ck_transports_comment_normalized"),
        "transports",
        "comment IS NULL OR (char_length(comment) <= 2000 AND "
        "char_length(btrim(comment)) > 0 AND comment = btrim(comment))",
    )
    op.create_check_constraint(
        op.f("ck_transports_debt_amount_non_negative"),
        "transports",
        "debt_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_transports_debt_amount_non_negative"),
        "transports",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_transports_comment_normalized"),
        "transports",
        type_="check",
    )
    op.drop_column("transports", "debt_amount")
    op.drop_column("transports", "comment")
