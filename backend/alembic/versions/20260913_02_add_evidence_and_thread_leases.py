"""Add evidence records and thread lease tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260913_02"
down_revision: str | None = "20260913_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tool_executions",
        sa.Column("mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "tool_executions",
        sa.Column("caller_id", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_id", sa.String(length=160), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        # canonical_url itself is never indexed: VARCHAR(2048) exceeds the
        # InnoDB key limit under utf8mb4; the fixed-length hash stands in.
        sa.Column("canonical_url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_quality", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "evidence_id", name="ux_evidence_records_identity"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "canonical_url_hash",
            "version",
            name="ux_evidence_records_version",
        ),
    )
    op.create_index(
        "ix_evidence_records_source",
        "evidence_records",
        ["tenant_id", "canonical_url_hash", "status"],
    )

    op.create_table(
        "thread_leases",
        sa.Column("thread_id", sa.String(length=128), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tool_executions", "mode")
    op.drop_column("tool_executions", "caller_id")
    op.drop_table("thread_leases")
    op.drop_index(
        "ix_evidence_records_source", table_name="evidence_records"
    )
    op.drop_table("evidence_records")
