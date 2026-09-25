"""add CRM contracts and work order contract link

Revision ID: 0021_crm_contracts
Revises: 0020_crm_core
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_crm_contracts"
down_revision = "0020_crm_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_number", sa.String(length=120), nullable=False),
        sa.Column("contract_type", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="aktív"),
        sa.Column("sla", sa.Text(), nullable=True),
        sa.Column("billing_model", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("contract_number", name="uq_crm_contracts_contract_number"),
    )
    op.create_index("ix_crm_contracts_customer_id", "crm_contracts", ["customer_id"])
    op.create_index("ix_crm_contracts_contract_number", "crm_contracts", ["contract_number"])
    op.create_index("ix_crm_contracts_contract_type", "crm_contracts", ["contract_type"])
    op.create_index("ix_crm_contracts_status", "crm_contracts", ["status"])
    op.create_index("ix_crm_contracts_start_date", "crm_contracts", ["start_date"])
    op.create_index("ix_crm_contracts_end_date", "crm_contracts", ["end_date"])
    op.create_index("ix_crm_contracts_customer_status", "crm_contracts", ["customer_id", "status"])
    op.create_index("ix_crm_contracts_dates", "crm_contracts", ["start_date", "end_date"])

    op.create_table(
        "crm_contract_locations",
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("crm_contracts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_index("ix_crm_contract_locations_location_id", "crm_contract_locations", ["location_id"])

    op.create_table(
        "crm_contract_assets",
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("crm_contracts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_index("ix_crm_contract_assets_asset_id", "crm_contract_assets", ["asset_id"])

    with op.batch_alter_table("work_orders") as batch:
        batch.add_column(sa.Column("contract_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_work_orders_contract_id", "crm_contracts", ["contract_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_work_orders_contract_id", ["contract_id"])


def downgrade():
    with op.batch_alter_table("work_orders") as batch:
        batch.drop_index("ix_work_orders_contract_id")
        batch.drop_constraint("fk_work_orders_contract_id", type_="foreignkey")
        batch.drop_column("contract_id")
    op.drop_table("crm_contract_assets")
    op.drop_table("crm_contract_locations")
    op.drop_table("crm_contracts")
