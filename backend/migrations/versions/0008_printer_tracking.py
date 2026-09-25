"""Add printer meter readings, tracked components and replacements.

Revision ID: 0008_printer_tracking
Revises: 0007_work_order_edit_presence
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_printer_tracking"
down_revision = "0007_work_order_edit_presence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_meter_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("asset_id", "recorded_at", name="uq_asset_meter_recorded_at"),
    )
    op.create_index("ix_asset_meter_readings_asset_id", "asset_meter_readings", ["asset_id"])
    op.create_index("ix_asset_meter_readings_recorded_at", "asset_meter_readings", ["recorded_at"])
    op.create_index("ix_asset_meter_readings_work_order_id", "asset_meter_readings", ["work_order_id"])
    op.create_index("ix_asset_meter_readings_recorded_by_user_id", "asset_meter_readings", ["recorded_by_user_id"])

    op.create_table(
        "asset_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("part_number", sa.String(length=150), nullable=True),
        sa.Column("expected_life_pages", sa.BigInteger(), nullable=True),
        sa.Column("last_replacement_at", sa.DateTime(), nullable=True),
        sa.Column("last_replacement_meter", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_asset_components_asset_id", "asset_components", ["asset_id"])
    op.create_index("ix_asset_components_name", "asset_components", ["name"])
    op.create_index("ix_asset_components_part_number", "asset_components", ["part_number"])

    op.create_table(
        "asset_component_replacements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("asset_component_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("technician_id", sa.Integer(), nullable=True),
        sa.Column("replaced_at", sa.DateTime(), nullable=False),
        sa.Column("meter_value", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_component_id"], ["asset_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["technician_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_asset_component_replacements_asset_id", "asset_component_replacements", ["asset_id"])
    op.create_index("ix_asset_component_replacements_asset_component_id", "asset_component_replacements", ["asset_component_id"])
    op.create_index("ix_asset_component_replacements_material_id", "asset_component_replacements", ["material_id"])
    op.create_index("ix_asset_component_replacements_work_order_id", "asset_component_replacements", ["work_order_id"])
    op.create_index("ix_asset_component_replacements_technician_id", "asset_component_replacements", ["technician_id"])
    op.create_index("ix_asset_component_replacements_replaced_at", "asset_component_replacements", ["replaced_at"])


def downgrade() -> None:
    op.drop_index("ix_asset_component_replacements_replaced_at", table_name="asset_component_replacements")
    op.drop_index("ix_asset_component_replacements_technician_id", table_name="asset_component_replacements")
    op.drop_index("ix_asset_component_replacements_work_order_id", table_name="asset_component_replacements")
    op.drop_index("ix_asset_component_replacements_material_id", table_name="asset_component_replacements")
    op.drop_index("ix_asset_component_replacements_asset_component_id", table_name="asset_component_replacements")
    op.drop_index("ix_asset_component_replacements_asset_id", table_name="asset_component_replacements")
    op.drop_table("asset_component_replacements")

    op.drop_index("ix_asset_components_part_number", table_name="asset_components")
    op.drop_index("ix_asset_components_name", table_name="asset_components")
    op.drop_index("ix_asset_components_asset_id", table_name="asset_components")
    op.drop_table("asset_components")

    op.drop_index("ix_asset_meter_readings_recorded_by_user_id", table_name="asset_meter_readings")
    op.drop_index("ix_asset_meter_readings_work_order_id", table_name="asset_meter_readings")
    op.drop_index("ix_asset_meter_readings_recorded_at", table_name="asset_meter_readings")
    op.drop_index("ix_asset_meter_readings_asset_id", table_name="asset_meter_readings")
    op.drop_table("asset_meter_readings")
