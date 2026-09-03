"""add receipt tags

Revision ID: 8e6f2c9a1b4d
Revises: 152cb29635aa
Create Date: 2026-09-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e6f2c9a1b4d"
down_revision: str | Sequence[str] | None = "152cb29635aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipt_tags",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0 AND name = btrim(name)",
            name=op.f("ck_receipt_tags_name_trimmed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipt_tags")),
    )
    op.create_index(
        "ix_receipt_tags_keyset",
        "receipt_tags",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        "uq_receipt_tags_name_ci",
        "receipt_tags",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.add_column("receipts", sa.Column("tag_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_receipts_tag_id_receipt_tags"),
        "receipts",
        "receipt_tags",
        ["tag_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_receipts_tag_keyset",
        "receipts",
        [
            "tag_id",
            sa.literal_column("created_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_receipts_tag_keyset", table_name="receipts")
    op.drop_constraint(
        op.f("fk_receipts_tag_id_receipt_tags"),
        "receipts",
        type_="foreignkey",
    )
    op.drop_column("receipts", "tag_id")
    op.drop_index("uq_receipt_tags_name_ci", table_name="receipt_tags")
    op.drop_index("ix_receipt_tags_keyset", table_name="receipt_tags")
    op.drop_table("receipt_tags")
