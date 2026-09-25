"""add contract type to work orders

Revision ID: 0016_work_order_contract_type
Revises: 0015_secondary_technician
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_work_order_contract_type"
down_revision = "0015_secondary_technician"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("contract_type", sa.String(length=120), nullable=True))


def downgrade():
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("contract_type")
