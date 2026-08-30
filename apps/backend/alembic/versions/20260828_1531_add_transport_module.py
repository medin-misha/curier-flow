"""add transport module

Revision ID: e265b38e8f8d
Revises: b9f51ffd0640
Create Date: 2026-08-28 15:31:46.382672
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e265b38e8f8d"
down_revision: str | Sequence[str] | None = "b9f51ffd0640"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "transports",
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("serial_number", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=64), nullable=False),
        sa.Column("deposit_required", sa.Boolean(), nullable=False),
        sa.Column("deposit_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("rental_price", sa.Numeric(precision=12, scale=2), nullable=False),
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
            "(deposit_required IS FALSE AND deposit_amount IS NULL) OR "
            "(deposit_required IS TRUE AND deposit_amount > 0)",
            name=op.f("ck_transports_deposit_state"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(color)) > 0 AND color = btrim(color)",
            name=op.f("ck_transports_color_trimmed"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(model)) > 0 AND model = btrim(model)",
            name=op.f("ck_transports_model_trimmed"),
        ),
        sa.CheckConstraint(
            "char_length(serial_number) > 0 AND serial_number = upper(btrim(serial_number))",
            name=op.f("ck_transports_serial_number_normalized"),
        ),
        sa.CheckConstraint(
            "char_length(type) > 0 AND type = lower(btrim(type))",
            name=op.f("ck_transports_type_normalized"),
        ),
        sa.CheckConstraint(
            "rental_price > 0",
            name=op.f("ck_transports_rental_price_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transports")),
        sa.UniqueConstraint("serial_number", name=op.f("uq_transports_serial_number")),
    )
    op.create_index(
        "ix_transports_keyset",
        "transports",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_table(
        "courier_transports",
        sa.Column("transport_id", sa.Uuid(), nullable=False),
        sa.Column("courier_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_id", sa.Uuid(), nullable=True),
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
        postgresql.ExcludeConstraint(
            (sa.column("courier_id"), "="),
            (sa.text("tstzrange(started_at, ended_at, '[)')"), "&&"),
            using="gist",
            name="excl_courier_transports_courier_period",
        ),
        postgresql.ExcludeConstraint(
            (sa.column("transport_id"), "="),
            (sa.text("tstzrange(started_at, ended_at, '[)')"), "&&"),
            using="gist",
            name="excl_courier_transports_transport_period",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at > started_at",
            name=op.f("ck_courier_transports_period_order"),
        ),
        sa.ForeignKeyConstraint(
            ["courier_id"],
            ["couriers.id"],
            name=op.f("fk_courier_transports_courier_id_couriers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_courier_transports_file_id_files"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transport_id"],
            ["transports.id"],
            name=op.f("fk_courier_transports_transport_id_transports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courier_transports")),
        sa.UniqueConstraint("file_id", name=op.f("uq_courier_transports_file_id")),
    )
    op.create_index(
        "ix_courier_transports_transport_keyset",
        "courier_transports",
        [
            "transport_id",
            sa.literal_column("created_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )
    op.create_table(
        "transport_components",
        sa.Column("transport_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
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
            name=op.f("ck_transport_components_name_trimmed"),
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name=op.f("ck_transport_components_quantity_positive"),
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name=op.f("ck_transport_components_unit_price_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["transport_id"],
            ["transports.id"],
            name=op.f("fk_transport_components_transport_id_transports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transport_components")),
        sa.UniqueConstraint(
            "transport_id",
            "name",
            name=op.f("uq_transport_components_transport_id_name"),
        ),
    )
    op.create_index(
        "ix_transport_components_transport_keyset",
        "transport_components",
        [
            "transport_id",
            sa.literal_column("created_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION transport_require_ready_contract_file()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            file_ready boolean;
        BEGIN
            IF NEW.file_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT status = 'ready'
            INTO file_ready
            FROM files
            WHERE id = NEW.file_id
            FOR UPDATE;

            IF FOUND AND NOT file_ready THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'contract_file_not_ready',
                    MESSAGE = 'contract file must be ready';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER transport_require_ready_contract_file
        BEFORE INSERT OR UPDATE OF file_id ON courier_transports
        FOR EACH ROW
        EXECUTE FUNCTION transport_require_ready_contract_file()
        """
    )
    op.execute(
        """
        CREATE FUNCTION transport_protect_signed_rental()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF (TG_OP = 'DELETE' AND OLD.file_id IS NOT NULL)
                OR (
                    TG_OP = 'UPDATE'
                    AND OLD.file_id IS NOT NULL
                    AND NEW.file_id IS DISTINCT FROM OLD.file_id
                )
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'signed_contract_protects_rental',
                    MESSAGE = 'signed contract protects rental';
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
        CREATE TRIGGER transport_protect_signed_rental
        BEFORE DELETE OR UPDATE OF file_id ON courier_transports
        FOR EACH ROW
        EXECUTE FUNCTION transport_protect_signed_rental()
        """
    )
    op.execute(
        """
        CREATE FUNCTION transport_protect_contract_file()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected boolean := false;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                SELECT EXISTS (
                    SELECT 1 FROM courier_transports WHERE file_id = OLD.id
                ) INTO protected;
            ELSIF NEW.status = 'deleting' AND OLD.status IS DISTINCT FROM NEW.status THEN
                SELECT EXISTS (
                    SELECT 1 FROM courier_transports WHERE file_id = NEW.id
                ) INTO protected;
            END IF;

            IF protected THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'file_deletion_protected',
                    MESSAGE = 'file is protected by a signed contract';
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
        CREATE TRIGGER transport_protect_contract_file
        BEFORE DELETE OR UPDATE OF status ON files
        FOR EACH ROW
        EXECUTE FUNCTION transport_protect_contract_file()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER transport_protect_contract_file ON files")
    op.execute("DROP FUNCTION transport_protect_contract_file()")
    op.execute("DROP TRIGGER transport_protect_signed_rental ON courier_transports")
    op.execute("DROP FUNCTION transport_protect_signed_rental()")
    op.execute("DROP TRIGGER transport_require_ready_contract_file ON courier_transports")
    op.execute("DROP FUNCTION transport_require_ready_contract_file()")
    op.drop_index(
        "ix_transport_components_transport_keyset",
        table_name="transport_components",
    )
    op.drop_table("transport_components")
    op.drop_index(
        "ix_courier_transports_transport_keyset",
        table_name="courier_transports",
    )
    op.drop_table("courier_transports")
    op.drop_index("ix_transports_keyset", table_name="transports")
    op.drop_table("transports")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
