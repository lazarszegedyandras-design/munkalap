"""push notification delivery outbox

Revision ID: 0032_push_notifications
Revises: 0031_mobile_photos
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_push_notifications"
down_revision = "0031_mobile_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mobile_devices", sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mobile_devices", sa.Column("push_token_updated_at", sa.DateTime(), nullable=True))

    op.create_table(
        "push_delivery_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("device_id", "dedupe_key", name="uq_push_delivery_device_dedupe"),
    )
    op.create_index("ix_push_delivery_outbox_user_id", "push_delivery_outbox", ["user_id"])
    op.create_index("ix_push_delivery_outbox_device_id", "push_delivery_outbox", ["device_id"])
    op.create_index("ix_push_delivery_outbox_notification_id", "push_delivery_outbox", ["notification_id"])
    op.create_index("ix_push_delivery_outbox_status", "push_delivery_outbox", ["status"])
    op.create_index("ix_push_delivery_outbox_next_attempt_at", "push_delivery_outbox", ["next_attempt_at"])
    op.create_index("ix_push_delivery_status_due", "push_delivery_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_push_delivery_user_created", "push_delivery_outbox", ["user_id", "created_at"])


def downgrade():
    op.drop_table("push_delivery_outbox")
    op.drop_column("mobile_devices", "push_token_updated_at")
    op.drop_column("mobile_devices", "push_enabled")
