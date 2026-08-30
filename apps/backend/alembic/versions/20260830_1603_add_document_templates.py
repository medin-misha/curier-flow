"""add document templates

Revision ID: 24b7f71bec0b
Revises: 9ac89161f490
Create Date: 2026-08-30 16:03:33.560745
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "24b7f71bec0b"
down_revision: str | Sequence[str] | None = "9ac89161f490"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            "jsonb_typeof(fields) = 'object'",
            name=op.f("ck_document_templates_fields_object"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0 AND name = btrim(name)",
            name=op.f("ck_document_templates_name_trimmed"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_document_templates_file_id_files"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_templates")),
        sa.UniqueConstraint("file_id", name=op.f("uq_document_templates_file_id")),
    )
    op.create_index(
        "ix_document_templates_keyset",
        "document_templates",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION documents_require_ready_template_file()
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
                    CONSTRAINT = 'document_template_file_not_ready',
                    MESSAGE = 'document template file must be ready';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER documents_require_ready_template_file
        BEFORE INSERT OR UPDATE OF file_id ON document_templates
        FOR EACH ROW
        EXECUTE FUNCTION documents_require_ready_template_file()
        """
    )
    op.execute(
        """
        CREATE FUNCTION documents_protect_template_file()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected boolean := false;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                SELECT EXISTS (
                    SELECT 1 FROM document_templates WHERE file_id = OLD.id
                ) INTO protected;
            ELSIF NEW.status = 'deleting' AND OLD.status IS DISTINCT FROM NEW.status THEN
                SELECT EXISTS (
                    SELECT 1 FROM document_templates WHERE file_id = NEW.id
                ) INTO protected;
            END IF;

            IF protected THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'file_deletion_protected',
                    MESSAGE = 'file is protected by a document template';
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
        CREATE TRIGGER documents_protect_template_file
        BEFORE DELETE OR UPDATE OF status ON files
        FOR EACH ROW
        EXECUTE FUNCTION documents_protect_template_file()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER documents_protect_template_file ON files")
    op.execute("DROP FUNCTION documents_protect_template_file()")
    op.execute("DROP TRIGGER documents_require_ready_template_file ON document_templates")
    op.execute("DROP FUNCTION documents_require_ready_template_file()")
    op.drop_index("ix_document_templates_keyset", table_name="document_templates")
    op.drop_table("document_templates")
