"""add finance receipts

Revision ID: 9ac89161f490
Revises: e265b38e8f8d
Create Date: 2026-08-30 15:07:37.657698
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9ac89161f490"
down_revision: str | Sequence[str] | None = "e265b38e8f8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_receipts_amount_positive")),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_receipts_file_id_files"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        sa.UniqueConstraint("file_id", name=op.f("uq_receipts_file_id")),
    )
    op.create_index(
        "ix_receipts_keyset",
        "receipts",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION finance_require_ready_receipt_file()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            file_ready boolean;
        BEGIN
            SELECT status = 'ready'
            INTO file_ready
            FROM files
            WHERE id = NEW.file_id
            FOR UPDATE;

            IF FOUND AND NOT file_ready THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'receipt_file_not_ready',
                    MESSAGE = 'receipt file must be ready';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER finance_require_ready_receipt_file
        BEFORE INSERT OR UPDATE OF file_id ON receipts
        FOR EACH ROW
        EXECUTE FUNCTION finance_require_ready_receipt_file()
        """
    )
    op.execute(
        """
        CREATE FUNCTION finance_protect_receipt_file()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected boolean := false;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                SELECT EXISTS (
                    SELECT 1 FROM receipts WHERE file_id = OLD.id
                ) INTO protected;
            ELSIF NEW.status = 'deleting' AND OLD.status IS DISTINCT FROM NEW.status THEN
                SELECT EXISTS (
                    SELECT 1 FROM receipts WHERE file_id = NEW.id
                ) INTO protected;
            END IF;

            IF protected THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'file_deletion_protected',
                    MESSAGE = 'file is protected by a receipt';
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER finance_protect_receipt_file
        BEFORE DELETE OR UPDATE OF status ON files
        FOR EACH ROW
        EXECUTE FUNCTION finance_protect_receipt_file()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER finance_protect_receipt_file ON files")
    op.execute("DROP FUNCTION finance_protect_receipt_file()")
    op.execute("DROP TRIGGER finance_require_ready_receipt_file ON receipts")
    op.execute("DROP FUNCTION finance_require_ready_receipt_file()")
    op.drop_index("ix_receipts_keyset", table_name="receipts")
    op.drop_table("receipts")
