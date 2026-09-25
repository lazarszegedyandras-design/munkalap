"""Add contract maintenance cycle fields to assets.

Revision ID: 0010_asset_maintenance_cycle
Revises: 0009_asset_list_performance
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_asset_maintenance_cycle"
down_revision = "0009_asset_list_performance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("maintenance_cycle_months", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("maintenance_cycle_note", sa.String(length=255), nullable=True))
    op.create_index("ix_assets_maintenance_cycle_months", "assets", ["maintenance_cycle_months"])
    op.create_index("ix_assets_last_maintenance_date", "assets", ["last_maintenance_date"])
    op.create_index(
        "ix_assets_maintenance_cycle",
        "assets",
        ["maintenance_cycle_months", "last_maintenance_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_assets_maintenance_cycle", table_name="assets")
    op.drop_index("ix_assets_last_maintenance_date", table_name="assets")
    op.drop_index("ix_assets_maintenance_cycle_months", table_name="assets")
    op.drop_column("assets", "maintenance_cycle_note")
    op.drop_column("assets", "maintenance_cycle_months")
