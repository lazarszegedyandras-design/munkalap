"""add secondary technician to work orders

Revision ID: 0015_secondary_technician
Revises: 0014_user_password_policy
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_secondary_technician"
down_revision = "0014_user_password_policy"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("secondary_technician_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_work_orders_secondary_technician_id_users",
            "users",
            ["secondary_technician_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_work_orders_secondary_technician_planned",
            ["secondary_technician_id", "planned_date"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_index("ix_work_orders_secondary_technician_planned")
        batch_op.drop_constraint("fk_work_orders_secondary_technician_id_users", type_="foreignkey")
        batch_op.drop_column("secondary_technician_id")
