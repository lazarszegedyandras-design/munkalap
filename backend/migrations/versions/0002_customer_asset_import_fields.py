"""customer and asset import fields

Revision ID: 0002_import_fields
Revises: 0001_initial
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_import_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("company_code", sa.String(length=50), nullable=True))
    op.create_index("ix_customers_company_code", "customers", ["company_code"])

    op.add_column("assets", sa.Column("company_code", sa.String(length=50), nullable=True))
    op.add_column("assets", sa.Column("import_source", sa.String(length=255), nullable=True))
    op.add_column("assets", sa.Column("import_batch", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("import_row", sa.Integer(), nullable=True))
    op.create_index("ix_assets_company_code", "assets", ["company_code"])
    op.create_index("ix_assets_import_batch", "assets", ["import_batch"])
    op.create_index("ix_assets_import_row", "assets", ["import_row"])


def downgrade() -> None:
    op.drop_index("ix_assets_import_row", table_name="assets")
    op.drop_index("ix_assets_import_batch", table_name="assets")
    op.drop_index("ix_assets_company_code", table_name="assets")
    op.drop_column("assets", "import_row")
    op.drop_column("assets", "import_batch")
    op.drop_column("assets", "import_source")
    op.drop_column("assets", "company_code")

    op.drop_index("ix_customers_company_code", table_name="customers")
    op.drop_column("customers", "company_code")
