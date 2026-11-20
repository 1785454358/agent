"""Retire custom trace storage after moving observation to LangSmith.

Revision ID: 20261109_02
Revises: 20261109_01
"""
import importlib.util
from pathlib import Path

from alembic import op

revision = "20261109_02"
down_revision = "20261109_01"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("trace_events")
    op.drop_table("trace_spans")


def downgrade():
    # Recreate the historical schema exactly; retired records cannot be restored.
    spec = importlib.util.spec_from_file_location("historical_trace_schema",
        Path(__file__).with_name("20261109_01_add_execution_traces.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.upgrade()
