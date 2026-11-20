"""Separate research sufficiency from execution completion.

Revision ID: 20261108_01
Revises: 20261010_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20261108_01"
down_revision = "20261010_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("research_runs", sa.Column(
        "research_sufficiency", sa.String(32), nullable=False, server_default="unknown",
    ))


def downgrade():
    op.drop_column("research_runs", "research_sufficiency")
