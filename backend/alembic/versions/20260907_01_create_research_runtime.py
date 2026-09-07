"""Create durable research runtime tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260907_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("research_runs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("termination_reason", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("search_queries", sa.JSON(), nullable=False),
        sa.Column("unresolved_gaps", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_runs_created_at", "research_runs", ["created_at"])
    op.create_index("ix_research_runs_status", "research_runs", ["status"])

    op.create_table("run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_events_created_at", "run_events", ["created_at"])
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_run_events_run_id_id", "run_events", ["run_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_run_events_run_id_id", table_name="run_events")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_index("ix_run_events_created_at", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_research_runs_status", table_name="research_runs")
    op.drop_index("ix_research_runs_created_at", table_name="research_runs")
    op.drop_table("research_runs")
