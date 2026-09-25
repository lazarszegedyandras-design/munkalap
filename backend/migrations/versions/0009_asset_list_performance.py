"""Add indexes for paginated asset list filtering and sorting.

Revision ID: 0009_asset_list_performance
Revises: 0008_printer_tracking
"""
from alembic import op

revision = "0009_asset_list_performance"
down_revision = "0008_printer_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_locations_customer_id", "locations", ["customer_id"])
    op.create_index("ix_assets_customer_id", "assets", ["customer_id"])
    op.create_index("ix_assets_current_location_id", "assets", ["current_location_id"])
    op.create_index("ix_assets_manufacturer", "assets", ["manufacturer"])
    op.create_index("ix_assets_model", "assets", ["model"])
    op.create_index("ix_assets_company_status", "assets", ["company_code", "status"])
    op.create_index("ix_assets_customer_location", "assets", ["customer_id", "current_location_id"])
    op.create_index("ix_assets_status_next_maintenance", "assets", ["status", "next_maintenance_date"])
    op.create_index("ix_asset_meter_asset_recorded", "asset_meter_readings", ["asset_id", "recorded_at"])
    op.create_index("ix_asset_components_asset_active", "asset_components", ["asset_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_asset_components_asset_active", table_name="asset_components")
    op.drop_index("ix_asset_meter_asset_recorded", table_name="asset_meter_readings")
    op.drop_index("ix_assets_status_next_maintenance", table_name="assets")
    op.drop_index("ix_assets_customer_location", table_name="assets")
    op.drop_index("ix_assets_company_status", table_name="assets")
    op.drop_index("ix_assets_model", table_name="assets")
    op.drop_index("ix_assets_manufacturer", table_name="assets")
    op.drop_index("ix_assets_current_location_id", table_name="assets")
    op.drop_index("ix_assets_customer_id", table_name="assets")
    op.drop_index("ix_locations_customer_id", table_name="locations")
