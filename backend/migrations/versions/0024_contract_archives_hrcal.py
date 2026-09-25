"""extend CRM contracts, add contract PDF archives, HR calendar support

Revision ID: 0024_contract_archives_hrcal
Revises: 0023_hr_leave_source_import
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_contract_archives_hrcal"
down_revision = "0023_hr_leave_source_import"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("crm_contracts") as batch:
        batch.add_column(sa.Column("company_code", sa.String(length=8), nullable=False, server_default="DRH"))
        batch.add_column(sa.Column("contracting_party_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("contracting_party_address", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("subject", sa.Text(), nullable=True))
        batch.add_column(sa.Column("term_text", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("billing_frequency", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("payment_terms", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("billing_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("service_confirmation", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("e_invoice_email", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("price_adjustment_terms", sa.Text(), nullable=True))
        batch.create_index("ix_crm_contracts_company_code", ["company_code"])

    op.create_table(
        "crm_contract_service_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("crm_contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rental_fee", sa.Text(), nullable=True),
        sa.Column("operating_fee", sa.Text(), nullable=True),
        sa.Column("click_fee", sa.Text(), nullable=True),
        sa.Column("included_quantity", sa.Text(), nullable=True),
        sa.Column("operator_company", sa.String(length=255), nullable=True),
        sa.Column("operator_site", sa.String(length=500), nullable=True),
        sa.Column("maintenance_cycle", sa.String(length=120), nullable=True),
        sa.Column("device_group", sa.String(length=255), nullable=True),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("serial_number", sa.String(length=255), nullable=True),
        sa.Column("parts_terms", sa.Text(), nullable=True),
        sa.Column("toner_terms", sa.Text(), nullable=True),
        sa.Column("travel_labor_terms", sa.Text(), nullable=True),
        sa.Column("repair_terms", sa.Text(), nullable=True),
        sa.Column("sla", sa.Text(), nullable=True),
        sa.Column("replacement_device", sa.Text(), nullable=True),
    )
    op.create_index("ix_crm_contract_service_lines_contract_id", "crm_contract_service_lines", ["contract_id"])

    op.create_table(
        "crm_contract_archives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("archive_number", sa.String(length=50), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("crm_contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("archive_number", name="uq_crm_contract_archives_archive_number"),
        sa.UniqueConstraint("storage_key", name="uq_crm_contract_archives_storage_key"),
    )
    op.create_index("ix_crm_contract_archives_contract_id", "crm_contract_archives", ["contract_id"])
    op.create_index("ix_crm_contract_archives_archive_number", "crm_contract_archives", ["archive_number"])
    op.create_index("ix_crm_contract_archives_sha256", "crm_contract_archives", ["sha256"])
    op.create_index("ix_crm_contract_archives_created_at", "crm_contract_archives", ["created_at"])
    op.create_index("ix_crm_contract_archives_uploaded_by_user_id", "crm_contract_archives", ["uploaded_by_user_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE SEQUENCE IF NOT EXISTS crm_contract_archive_number_seq START 1")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP SEQUENCE IF EXISTS crm_contract_archive_number_seq")
    op.drop_table("crm_contract_archives")
    op.drop_table("crm_contract_service_lines")
    with op.batch_alter_table("crm_contracts") as batch:
        batch.drop_index("ix_crm_contracts_company_code")
        batch.drop_column("price_adjustment_terms")
        batch.drop_column("e_invoice_email")
        batch.drop_column("service_confirmation")
        batch.drop_column("billing_name")
        batch.drop_column("payment_terms")
        batch.drop_column("billing_frequency")
        batch.drop_column("term_text")
        batch.drop_column("subject")
        batch.drop_column("contracting_party_address")
        batch.drop_column("contracting_party_name")
        batch.drop_column("company_code")
