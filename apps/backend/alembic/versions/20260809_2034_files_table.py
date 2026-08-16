"""files table

Revision ID: ddafc759322a
Revises: 820a195cdadf
Create Date: 2026-08-09 20:34:44.069970
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ddafc759322a"
down_revision: str | Sequence[str] | None = "820a195cdadf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("key", sa.String(length=1024), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("etag", sa.String(length=128), nullable=True),
        # VARCHAR, а не нативный enum Postgres: новое состояние файла — это
        # правка кода, а не ALTER TYPE, который к тому же не откатывается
        # внутри транзакции миграции.
        sa.Column(
            "status",
            sa.Enum(
                "pending", "ready", "deleting", name="file_status", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        # Две строки на один объект — это потерянный объект: уборка одной из
        # них удалила бы объект из-под второй.
        sa.UniqueConstraint("bucket", "key", name=op.f("uq_files_bucket_key")),
    )
    # Индекс под keyset-пагинацию. Направление обязано совпадать с
    # `ORDER BY created_at DESC, id DESC` из CRUD.list_page: индекс по
    # возрастанию Postgres тоже прочитает назад, но составной ключ с разным
    # направлением колонок — уже нет.
    op.create_index(
        "ix_files_keyset",
        "files",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    # Выборка обеих периодических задач: «pending старше TTL» и «deleting».
    op.create_index("ix_files_status_created_at", "files", ["status", "created_at"], unique=False)


def downgrade() -> None:
    # Индексы отдельно не удаляются: DROP TABLE уносит их вместе с таблицей.
    op.drop_table("files")
