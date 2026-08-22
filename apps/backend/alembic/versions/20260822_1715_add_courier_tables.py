"""add courier tables

Revision ID: 703019fec8e5
Revises: 6b2a7c9d0e14
Create Date: 2026-08-22 17:15:56.528121
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "703019fec8e5"
down_revision: str | Sequence[str] | None = "6b2a7c9d0e14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "couriers",
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("citizenship", sa.String(length=128), nullable=True),
        sa.Column("bank_account", sa.String(length=64), nullable=True),
        sa.Column("contact_platform", sa.String(length=32), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("consent_to_processing", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
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
            "(consent_to_processing IS TRUE AND consent_at IS NOT NULL) OR "
            "(consent_to_processing IS FALSE AND consent_at IS NULL)",
            name=op.f("ck_couriers_consent_state"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_couriers")),
        sa.UniqueConstraint("email", name=op.f("uq_couriers_email")),
        sa.UniqueConstraint("phone", name=op.f("uq_couriers_phone")),
    )
    op.create_index(op.f("ix_couriers_full_name"), "couriers", ["full_name"], unique=False)
    op.create_index(
        "ix_couriers_keyset",
        "couriers",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_table(
        "courier_documents",
        sa.Column("courier_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "platform_onboarding",
                "employment_compliance",
                "other",
                name="document_purpose",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("legal_hold_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "passport",
                "identity_card",
                "residence_permit",
                "work_permit",
                "driving_license",
                "other",
                name="document_type",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["courier_id"],
            ["couriers.id"],
            name=op.f("fk_courier_documents_courier_id_couriers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_courier_documents_file_id_files"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courier_documents")),
        sa.UniqueConstraint("file_id", name=op.f("uq_courier_documents_file_id")),
    )
    op.create_index(
        "ix_courier_documents_courier_keyset",
        "courier_documents",
        ["courier_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_courier_documents_keyset",
        "courier_documents",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_courier_documents_legal_hold_until"),
        "courier_documents",
        ["legal_hold_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_courier_documents_purpose"), "courier_documents", ["purpose"], unique=False
    )
    op.create_index(
        "ix_courier_documents_retention",
        "courier_documents",
        ["type", "purpose", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_courier_documents_type"), "courier_documents", ["type"], unique=False)
    op.create_table(
        "courier_platform_accounts",
        sa.Column("courier_id", sa.Uuid(), nullable=False),
        sa.Column(
            "platform",
            sa.Enum(
                "bolt_food",
                "foodora",
                "wolt",
                name="delivery_platform",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "active",
                "inactive",
                name="platform_account_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["courier_id"],
            ["couriers.id"],
            name=op.f("fk_courier_platform_accounts_courier_id_couriers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courier_platform_accounts")),
        sa.UniqueConstraint(
            "courier_id", "platform", name=op.f("uq_courier_platform_accounts_courier_id_platform")
        ),
    )
    op.create_index(
        "ix_courier_platform_accounts_courier_keyset",
        "courier_platform_accounts",
        ["courier_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_courier_platform_accounts_keyset",
        "courier_platform_accounts",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_courier_platform_accounts_platform"),
        "courier_platform_accounts",
        ["platform"],
        unique=False,
    )
    op.create_index(
        op.f("ix_courier_platform_accounts_status"),
        "courier_platform_accounts",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_courier_platform_accounts_status"), table_name="courier_platform_accounts"
    )
    op.drop_index(
        op.f("ix_courier_platform_accounts_platform"), table_name="courier_platform_accounts"
    )
    op.drop_index("ix_courier_platform_accounts_keyset", table_name="courier_platform_accounts")
    op.drop_index(
        "ix_courier_platform_accounts_courier_keyset", table_name="courier_platform_accounts"
    )
    op.drop_table("courier_platform_accounts")
    op.drop_index(op.f("ix_courier_documents_type"), table_name="courier_documents")
    op.drop_index("ix_courier_documents_retention", table_name="courier_documents")
    op.drop_index(op.f("ix_courier_documents_purpose"), table_name="courier_documents")
    op.drop_index(op.f("ix_courier_documents_legal_hold_until"), table_name="courier_documents")
    op.drop_index("ix_courier_documents_keyset", table_name="courier_documents")
    op.drop_index("ix_courier_documents_courier_keyset", table_name="courier_documents")
    op.drop_table("courier_documents")
    op.drop_index("ix_couriers_keyset", table_name="couriers")
    op.drop_index(op.f("ix_couriers_full_name"), table_name="couriers")
    op.drop_table("couriers")
