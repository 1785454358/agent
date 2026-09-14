"""Add structured long-term-memory recall fields.

Revision ID: 20260914_01
Revises: 20260913_03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_01"
down_revision: str | None = "20260913_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_records", sa.Column("memory_id", sa.String(128)))
    op.add_column("memory_records", sa.Column("memory_type", sa.String(32)))
    op.add_column("memory_records", sa.Column("status", sa.String(32)))
    op.add_column("memory_records", sa.Column("importance", sa.Float()))
    op.add_column("memory_records", sa.Column("confidence", sa.Float()))
    op.add_column("memory_records", sa.Column("created_at", sa.DateTime(timezone=True)))
    op.add_column("memory_records", sa.Column("expires_at", sa.DateTime(timezone=True)))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                "UPDATE memory_records SET "
                "memory_id = json_extract(payload, '$.id'), "
                "memory_type = json_extract(payload, '$.type'), "
                "status = json_extract(payload, '$.status'), "
                "importance = COALESCE(json_extract(payload, '$.importance'), 0.5), "
                "confidence = COALESCE(json_extract(payload, '$.confidence'), 0.8), "
                "created_at = updated_at"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE memory_records SET "
                "memory_id = JSON_UNQUOTE(JSON_EXTRACT(payload, '$.id')), "
                "memory_type = JSON_UNQUOTE(JSON_EXTRACT(payload, '$.type')), "
                "status = JSON_UNQUOTE(JSON_EXTRACT(payload, '$.status')), "
                "importance = COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.importance')) AS DECIMAL(10,6)), 0.5), "
                "confidence = COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.confidence')) AS DECIMAL(10,6)), 0.8), "
                "created_at = updated_at"
            )
        )

    with op.batch_alter_table("memory_records") as batch:
        for name, type_ in (
            ("memory_id", sa.String(128)),
            ("memory_type", sa.String(32)),
            ("status", sa.String(32)),
            ("importance", sa.Float()),
            ("confidence", sa.Float()),
            ("created_at", sa.DateTime(timezone=True)),
        ):
            batch.alter_column(name, existing_type=type_, nullable=False)

    op.create_index(
        "ix_memory_records_memory_id",
        "memory_records",
        ["memory_id"],
    )
    op.create_index(
        "ix_memory_records_recall",
        "memory_records",
        [
            "namespace_scope",
            "namespace_owner",
            "namespace_kind",
            "memory_type",
            "status",
            "expires_at",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_records_recall", table_name="memory_records")
    op.drop_index("ix_memory_records_memory_id", table_name="memory_records")
    with op.batch_alter_table("memory_records") as batch:
        for name in (
            "expires_at",
            "created_at",
            "confidence",
            "importance",
            "status",
            "memory_type",
            "memory_id",
        ):
            batch.drop_column(name)
