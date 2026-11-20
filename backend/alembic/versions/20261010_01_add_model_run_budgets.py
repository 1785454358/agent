"""Persist model admission counters, deadlines and observed usage.

Revision ID: 20261010_01
Revises: 20260914_01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261010_01"
down_revision = "20260914_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_run_budgets",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("model_run_budgets")
