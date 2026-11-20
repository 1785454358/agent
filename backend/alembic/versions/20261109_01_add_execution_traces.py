"""Persist hierarchical execution spans and correlated events.

Revision ID: 20261109_01
Revises: 20261108_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20261109_01"
down_revision = "20261108_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("trace_spans",
        sa.Column("span_id", sa.String(16), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("parent_span_id", sa.String(16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_trace_spans_run_id", "trace_spans", ["run_id"])
    op.create_index("ix_trace_spans_trace_id", "trace_spans", ["trace_id"])
    op.create_index("ix_trace_spans_run_parent_started", "trace_spans", ["run_id", "parent_span_id", "started_at"])
    op.create_table("trace_events",
        sa.Column("event_id", sa.String(32), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_trace_events_run_id", "trace_events", ["run_id"])


def downgrade():
    op.drop_table("trace_events")
    op.drop_table("trace_spans")
