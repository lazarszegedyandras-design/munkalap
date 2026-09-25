"""work order archives

Revision ID: 0012_work_order_archives
Revises: 0011_work_order_list_views
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_work_order_archives"
down_revision = "0011_work_order_list_views"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE SEQUENCE IF NOT EXISTS work_order_archive_number_seq START WITH 1")
    op.create_table(
        "work_order_archives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("archive_number", sa.String(length=50), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("source_number", sa.String(length=100), nullable=True),
        sa.Column("work_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_work_order_archives_archive_number", "work_order_archives", ["archive_number"], unique=True)
    op.create_index("ix_work_order_archives_work_order_id", "work_order_archives", ["work_order_id"], unique=False)
    op.create_index("ix_work_order_archives_source_number", "work_order_archives", ["source_number"], unique=False)
    op.create_index("ix_work_order_archives_work_date", "work_order_archives", ["work_date"], unique=False)
    op.create_index("ix_work_order_archives_sha256", "work_order_archives", ["sha256"], unique=False)
    op.create_index("ix_work_order_archives_uploaded_by_user_id", "work_order_archives", ["uploaded_by_user_id"], unique=False)
    op.create_index("ix_work_order_archives_created_at", "work_order_archives", ["created_at"], unique=False)

    op.create_table(
        "work_order_archive_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("archive_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["work_order_archives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("archive_id", "asset_id", name="uq_work_order_archive_asset"),
    )
    op.create_index("ix_work_order_archive_assets_archive_id", "work_order_archive_assets", ["archive_id"], unique=False)
    op.create_index("ix_work_order_archive_assets_asset_id", "work_order_archive_assets", ["asset_id"], unique=False)


def downgrade():
    op.drop_index("ix_work_order_archive_assets_asset_id", table_name="work_order_archive_assets")
    op.drop_index("ix_work_order_archive_assets_archive_id", table_name="work_order_archive_assets")
    op.drop_table("work_order_archive_assets")
    op.drop_index("ix_work_order_archives_created_at", table_name="work_order_archives")
    op.drop_index("ix_work_order_archives_uploaded_by_user_id", table_name="work_order_archives")
    op.drop_index("ix_work_order_archives_sha256", table_name="work_order_archives")
    op.drop_index("ix_work_order_archives_work_date", table_name="work_order_archives")
    op.drop_index("ix_work_order_archives_source_number", table_name="work_order_archives")
    op.drop_index("ix_work_order_archives_work_order_id", table_name="work_order_archives")
    op.drop_index("ix_work_order_archives_archive_number", table_name="work_order_archives")
    op.drop_table("work_order_archives")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP SEQUENCE IF EXISTS work_order_archive_number_seq")
