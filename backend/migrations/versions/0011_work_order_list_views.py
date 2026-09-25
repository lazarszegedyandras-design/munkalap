"""work order list performance and saved views

Revision ID: 0011_work_order_list_views
Revises: 0010_asset_maintenance_cycle
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_work_order_list_views"
down_revision = "0010_asset_maintenance_cycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_work_orders_status_planned", "work_orders", ["status", "planned_date"], unique=False)
    op.create_index("ix_work_orders_customer_planned", "work_orders", ["customer_id", "planned_date"], unique=False)
    op.create_index("ix_work_orders_technician_planned", "work_orders", ["technician_id", "planned_date"], unique=False)
    op.create_index("ix_work_orders_work_type_planned", "work_orders", ["work_type", "planned_date"], unique=False)
    op.create_index("ix_work_orders_created_at", "work_orders", ["created_at"], unique=False)

    op.create_table(
        "work_order_saved_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name", name="uq_work_order_saved_view_user_name"),
    )
    op.create_index("ix_work_order_saved_views_user_id", "work_order_saved_views", ["user_id"], unique=False)
    op.create_index("ix_work_order_saved_views_user_default", "work_order_saved_views", ["user_id", "is_default"], unique=False)


def downgrade():
    op.drop_index("ix_work_order_saved_views_user_default", table_name="work_order_saved_views")
    op.drop_index("ix_work_order_saved_views_user_id", table_name="work_order_saved_views")
    op.drop_table("work_order_saved_views")
    op.drop_index("ix_work_orders_created_at", table_name="work_orders")
    op.drop_index("ix_work_orders_work_type_planned", table_name="work_orders")
    op.drop_index("ix_work_orders_technician_planned", table_name="work_orders")
    op.drop_index("ix_work_orders_customer_planned", table_name="work_orders")
    op.drop_index("ix_work_orders_status_planned", table_name="work_orders")
