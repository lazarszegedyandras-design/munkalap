"""add detailed meter channels

Revision ID: 0013_meter_channels
Revises: 0012_work_order_archives
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_meter_channels"
down_revision = "0012_work_order_archives"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("asset_meter_readings", sa.Column("black_white_value", sa.BigInteger(), nullable=True))
    op.add_column("asset_meter_readings", sa.Column("color_value", sa.BigInteger(), nullable=True))
    op.add_column("asset_meter_readings", sa.Column("scan_value", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("asset_meter_readings", "scan_value")
    op.drop_column("asset_meter_readings", "color_value")
    op.drop_column("asset_meter_readings", "black_white_value")
