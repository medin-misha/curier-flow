"""add receipt date

Revision ID: 152cb29635aa
Revises: 24b7f71bec0b
Create Date: 2026-08-30 17:09:58.748285
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "152cb29635aa"
down_revision: str | Sequence[str] | None = "24b7f71bec0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("date", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE receipts
        SET date = (created_at AT TIME ZONE 'Europe/Prague')::date
        """
    )
    op.alter_column("receipts", "date", existing_type=sa.Date(), nullable=False)


def downgrade() -> None:
    op.drop_column("receipts", "date")
