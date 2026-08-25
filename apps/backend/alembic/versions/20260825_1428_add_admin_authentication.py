"""add admin authentication

Revision ID: b9f51ffd0640
Revises: 703019fec8e5
Create Date: 2026-08-25 14:28:37.550106
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9f51ffd0640"
down_revision: str | Sequence[str] | None = "703019fec8e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("hashed_password", sa.String(length=512), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("auth_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.CheckConstraint("auth_version > 0", name=op.f("ck_admins_auth_version_positive")),
        sa.CheckConstraint(
            "telegram_id IS NULL OR telegram_id > 0", name=op.f("ck_admins_telegram_id_positive")
        ),
        sa.CheckConstraint("username = lower(username)", name=op.f("ck_admins_username_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admins")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_admins_telegram_id")),
        sa.UniqueConstraint("username", name=op.f("uq_admins_username")),
    )
    op.create_index(
        "ix_admins_keyset",
        "admins",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_table(
        "admin_refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "auth_version > 0", name=op.f("ck_admin_refresh_tokens_auth_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admins.id"],
            name=op.f("fk_admin_refresh_tokens_admin_id_admins"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_admin_refresh_tokens_token_hash")),
    )
    op.create_index(
        "ix_admin_refresh_tokens_admin_active",
        "admin_refresh_tokens",
        ["admin_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_refresh_tokens_expires_at", "admin_refresh_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_admin_refresh_tokens_family_active",
        "admin_refresh_tokens",
        ["family_id", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_refresh_tokens_family_active", table_name="admin_refresh_tokens")
    op.drop_index("ix_admin_refresh_tokens_expires_at", table_name="admin_refresh_tokens")
    op.drop_index("ix_admin_refresh_tokens_admin_active", table_name="admin_refresh_tokens")
    op.drop_table("admin_refresh_tokens")
    op.drop_index("ix_admins_keyset", table_name="admins")
    op.drop_table("admins")
