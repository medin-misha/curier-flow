"""idempotency keys

Revision ID: 8f4f401e3143
Revises: ddafc759322a
Create Date: 2026-08-10 00:16:25.084747
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8f4f401e3143"
down_revision: str | Sequence[str] | None = "ddafc759322a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        # Ключ придумывает клиент, поэтому он же первичный: уникальность обязана
        # проверяться базой, а не запросом «а есть ли такая строка».
        sa.Column("key", sa.String(length=255), nullable=False),
        # Отпечаток метода, пути, действующего лица и тела запроса.
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        # VARCHAR, а не нативный enum Postgres: новое состояние — это правка
        # кода, а не ALTER TYPE, который к тому же не откатывается внутри
        # транзакции миграции.
        sa.Column(
            "status",
            sa.Enum(
                "in_progress",
                "completed",
                name="idempotency_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        # Ответ заполняется до коммита той же транзакцией, что и данные, но
        # колонки остаются nullable: у ответа, который нельзя воспроизвести
        # (потоковый), строка так и остаётся со статусом in_progress.
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", sa.LargeBinary(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_idempotency_keys")),
    )
    # Индекс под выборку уборки: `WHERE created_at < отсечка`.
    op.create_index(
        op.f("ix_idempotency_keys_created_at"), "idempotency_keys", ["created_at"], unique=False
    )
    # То же самое для отметок об обработанных сообщениях: их уборка появилась
    # вместе с уборкой ключей, а таблица растёт со скоростью всего потока
    # сообщений сервиса.
    op.create_index(
        op.f("ix_processed_messages_processed_at"),
        "processed_messages",
        ["processed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_processed_messages_processed_at"), table_name="processed_messages")
    # Индекс по created_at отдельно не удаляется: DROP TABLE уносит его вместе
    # с таблицей.
    op.drop_table("idempotency_keys")
