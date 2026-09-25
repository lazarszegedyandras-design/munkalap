"""Add work type to work orders.

Revision ID: 0005_work_order_type
Revises: 0004_work_order_planned_times
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_work_order_type"
down_revision = "0004_work_order_planned_times"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("work_type", sa.String(length=64), nullable=True))
    op.create_index("ix_work_orders_work_type", "work_orders", ["work_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_work_orders_work_type", table_name="work_orders")
    op.drop_column("work_orders", "work_type")
