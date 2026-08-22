"""file upload staging

Revision ID: 6b2a7c9d0e14
Revises: 8f4f401e3143
Create Date: 2026-08-22 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b2a7c9d0e14"
down_revision: str | Sequence[str] | None = "8f4f401e3143"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_upload_staging",
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("key", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "uploading",
                "uploaded",
                "deleting",
                name="staging_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("etag", sa.String(length=128), nullable=True),
        sa.Column("multipart_upload_id", sa.String(length=1024), nullable=True),
        sa.Column("cleanup_claim_token", sa.Uuid(), nullable=True),
        sa.Column("cleanup_claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_upload_staging")),
        sa.UniqueConstraint(
            "bucket",
            "key",
            name=op.f("uq_file_upload_staging_bucket_key"),
        ),
    )
    op.create_index(
        "ix_file_upload_staging_status_updated_at",
        "file_upload_staging",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_file_upload_staging_deleting_lease",
        "file_upload_staging",
        ["status", "cleanup_claimed_until", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("file_upload_staging")
