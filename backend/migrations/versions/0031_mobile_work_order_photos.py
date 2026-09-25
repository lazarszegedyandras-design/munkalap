"""mobile work-order photos

Revision ID: 0031_mobile_photos
Revises: 0030_mobile_signatures
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_mobile_photos"
down_revision = "0030_mobile_signatures"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_order_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mobile_device_id", sa.Integer(), sa.ForeignKey("mobile_devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_work_order_photos_work_order_id", "work_order_photos", ["work_order_id"])
    op.create_index("ix_work_order_photos_category", "work_order_photos", ["category"])
    op.create_index("ix_work_order_photos_uploaded_by_user_id", "work_order_photos", ["uploaded_by_user_id"])
    op.create_index("ix_work_order_photos_mobile_device_id", "work_order_photos", ["mobile_device_id"])
    op.create_index("ix_work_order_photos_created_at", "work_order_photos", ["created_at"])
    op.create_index("ix_work_order_photos_work_order_created", "work_order_photos", ["work_order_id", "created_at"])
    op.create_index("ix_work_order_photos_sha256", "work_order_photos", ["sha256"])


def downgrade():
    op.drop_table("work_order_photos")
