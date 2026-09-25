"""mobile API device sessions and immutable work-order signatures

Revision ID: 0030_mobile_signatures
Revises: 0029_cloud_security
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_mobile_signatures"
down_revision = "0029_cloud_security"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mobile_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_uuid", sa.String(length=128), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="android"),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("push_token", sa.String(length=512), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "device_uuid", name="uq_mobile_devices_user_uuid"),
    )
    op.create_index("ix_mobile_devices_user_id", "mobile_devices", ["user_id"])
    op.create_index("ix_mobile_devices_user_revoked", "mobile_devices", ["user_id", "revoked_at"])

    op.create_table(
        "mobile_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("refresh_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("absolute_expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("mfa_verified_at", sa.DateTime(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_mobile_sessions_session_id", "mobile_sessions", ["session_id"], unique=True)
    op.create_index("ix_mobile_sessions_user_id", "mobile_sessions", ["user_id"])
    op.create_index("ix_mobile_sessions_device_id", "mobile_sessions", ["device_id"])
    op.create_index("ix_mobile_sessions_user_revoked", "mobile_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_mobile_sessions_device_revoked", "mobile_sessions", ["device_id", "revoked_at"])
    op.create_index("ix_mobile_sessions_absolute_expires", "mobile_sessions", ["absolute_expires_at"])

    op.create_table(
        "work_order_completion_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_work_order_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("work_order_id", "revision", name="uq_work_order_completion_revision"),
    )
    op.create_index("ix_work_order_completion_work_order_id", "work_order_completion_snapshots", ["work_order_id"])
    op.create_index("ix_work_order_completion_created_by_user_id", "work_order_completion_snapshots", ["created_by_user_id"])
    op.create_index("ix_work_order_completion_work_order_created", "work_order_completion_snapshots", ["work_order_id", "created_at"])
    op.create_index("ix_work_order_completion_sha256", "work_order_completion_snapshots", ["snapshot_sha256"])

    op.create_table(
        "work_order_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("work_order_completion_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("signer_name", sa.String(length=255), nullable=False),
        sa.Column("signer_role", sa.String(length=255), nullable=True),
        sa.Column("acceptance_text", sa.Text(), nullable=False),
        sa.Column("acceptance_text_version", sa.String(length=32), nullable=False),
        sa.Column("signature_storage_key", sa.String(length=500), nullable=False),
        sa.Column("signature_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("signed_pdf_storage_key", sa.String(length=500), nullable=False),
        sa.Column("signed_pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("signed_pdf_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("finalized_work_order_version", sa.Integer(), nullable=False),
        sa.Column("technician_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mobile_device_id", sa.Integer(), sa.ForeignKey("mobile_devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("snapshot_id", name="uq_work_order_signatures_snapshot"),
        sa.UniqueConstraint("signature_storage_key", name="uq_work_order_signatures_signature_storage_key"),
        sa.UniqueConstraint("signed_pdf_storage_key", name="uq_work_order_signatures_pdf_storage_key"),
    )
    op.create_index("ix_work_order_signatures_snapshot_id", "work_order_signatures", ["snapshot_id"], unique=False)
    op.create_index("ix_work_order_signatures_work_order_id", "work_order_signatures", ["work_order_id"])
    op.create_index("ix_work_order_signatures_signature_sha256", "work_order_signatures", ["signature_sha256"])
    op.create_index("ix_work_order_signatures_technician_user_id", "work_order_signatures", ["technician_user_id"])
    op.create_index("ix_work_order_signatures_mobile_device_id", "work_order_signatures", ["mobile_device_id"])
    op.create_index("ix_work_order_signatures_signed_at", "work_order_signatures", ["signed_at"])
    op.create_index("ix_work_order_signatures_work_order_signed", "work_order_signatures", ["work_order_id", "signed_at"])
    op.create_index("ix_work_order_signatures_pdf_sha256", "work_order_signatures", ["signed_pdf_sha256"])


def downgrade():
    op.drop_table("work_order_signatures")
    op.drop_table("work_order_completion_snapshots")
    op.drop_table("mobile_sessions")
    op.drop_table("mobile_devices")
