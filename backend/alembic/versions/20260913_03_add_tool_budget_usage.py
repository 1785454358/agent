"""Add durable tool budget usage counters."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260913_03"
down_revision: str | None = "20260913_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in (
        "consumed_tool_calls",
        "consumed_network_requests",
        "consumed_fetched_pages",
    ):
        op.add_column(
            "tool_executions",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for name in (
        "consumed_fetched_pages",
        "consumed_network_requests",
        "consumed_tool_calls",
    ):
        op.drop_column("tool_executions", name)
