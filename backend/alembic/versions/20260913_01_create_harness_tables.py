"""Create harness checkpoint, tool ledger and memory tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260913_01"
down_revision: str | None = "20260907_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column(
            "thread_id",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.create_table(
        "graph_checkpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=256), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_blob", sa.LargeBinary(), nullable=False),
        sa.Column("metadata_blob", sa.LargeBinary(), nullable=False),
        sa.Column("metadata_type", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            name="ux_graph_checkpoints_identity",
        ),
    )
    op.create_index(
        "ix_graph_checkpoints_thread_id",
        "graph_checkpoints",
        ["thread_id"],
    )

    op.create_table(
        "graph_checkpoint_writes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=256), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("task_path", sa.String(length=256), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_graph_writes_task",
        "graph_checkpoint_writes",
        ["thread_id", "checkpoint_ns", "checkpoint_id", "task_id"],
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("call_id", sa.String(length=160), nullable=False),
        sa.Column("fingerprint", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("owner_token", sa.String(length=64), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "call_id",
            name="ux_tool_executions_identity",
        ),
    )

    op.create_table(
        "memory_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("namespace_scope", sa.String(length=32), nullable=False),
        sa.Column("namespace_owner", sa.String(length=128), nullable=False),
        sa.Column("namespace_kind", sa.String(length=64), nullable=False),
        sa.Column("store_key", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "namespace_scope",
            "namespace_owner",
            "namespace_kind",
            "store_key",
            name="ux_memory_records_key",
        ),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "thread_id")
    op.drop_table("memory_records")
    op.drop_table("tool_executions")
    op.drop_index(
        "ix_graph_writes_task", table_name="graph_checkpoint_writes"
    )
    op.drop_table("graph_checkpoint_writes")
    op.drop_index(
        "ix_graph_checkpoints_thread_id", table_name="graph_checkpoints"
    )
    op.drop_table("graph_checkpoints")
