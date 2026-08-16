"""outbox and processed messages

Revision ID: 820a195cdadf
Create Date: 2026-08-09 16:47:00.950207
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "820a195cdadf"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
    )
    op.create_index(op.f("ix_outbox_topic"), "outbox", ["topic"], unique=False)
    # Частичный индекс релея: в нём лежат только неопубликованные строки, то
    # есть хвост очереди, а не вся история. Колонки — ровно порядок выборки
    # (`ORDER BY occurred_at, id`), чтобы Postgres не досортировывал результат.
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["occurred_at", "id"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "processed_messages",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_processed_messages")),
    )


def downgrade() -> None:
    # Индексы отдельно не удаляются: DROP TABLE уносит их вместе с таблицей.
    op.drop_table("processed_messages")
    op.drop_table("outbox")
