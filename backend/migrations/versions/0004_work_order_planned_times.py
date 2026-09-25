"""Add planned start and end time to work orders.

Revision ID: 0004_work_order_planned_times
Revises: 0003_customer_contacts
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_work_order_planned_times"
down_revision = "0003_customer_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("planned_start_at", sa.DateTime(), nullable=True))
    op.add_column("work_orders", sa.Column("planned_end_at", sa.DateTime(), nullable=True))
    op.create_index("ix_work_orders_planned_start_at", "work_orders", ["planned_start_at"], unique=False)
    op.create_index("ix_work_orders_planned_end_at", "work_orders", ["planned_end_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_work_orders_planned_end_at", table_name="work_orders")
    op.drop_index("ix_work_orders_planned_start_at", table_name="work_orders")
    op.drop_column("work_orders", "planned_end_at")
    op.drop_column("work_orders", "planned_start_at")
