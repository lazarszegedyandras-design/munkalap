"""add procurement request workflow

Revision ID: 0028_procurement
Revises: 0027_leave_cancel_approval
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_procurement"
down_revision = "0027_leave_cancel_approval"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "procurement_request_sequences",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "procurement_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_number", sa.String(length=32), nullable=False),
        sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="HUF"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("approver_comment", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("total_amount > 0", name="ck_procurement_requests_total_amount_positive"),
    )
    op.create_index("ix_procurement_requests_request_number", "procurement_requests", ["request_number"], unique=True)
    op.create_index("ix_procurement_requests_requester_user_id", "procurement_requests", ["requester_user_id"])
    op.create_index("ix_procurement_requests_approved_by_user_id", "procurement_requests", ["approved_by_user_id"])
    op.create_index("ix_procurement_requests_status", "procurement_requests", ["status"])
    op.create_index("ix_procurement_requests_requester_status", "procurement_requests", ["requester_user_id", "status"])
    op.create_index("ix_procurement_requests_submitted_at", "procurement_requests", ["submitted_at"])
    op.create_index("ix_procurement_requests_status_submitted", "procurement_requests", ["status", "submitted_at"])

    op.create_table(
        "procurement_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("procurement_request_id", sa.Integer(), sa.ForeignKey("procurement_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("storage_key", name="uq_procurement_attachments_storage_key"),
    )
    op.create_index("ix_procurement_attachments_procurement_request_id", "procurement_attachments", ["procurement_request_id"])
    op.create_index("ix_procurement_attachments_uploaded_by_user_id", "procurement_attachments", ["uploaded_by_user_id"])
    op.create_index("ix_procurement_attachments_sha256", "procurement_attachments", ["sha256"])
    op.create_index("ix_procurement_attachments_request_created", "procurement_attachments", ["procurement_request_id", "created_at"])

    # A jog bekerül a katalógusba már a migráció során; a seed később idempotensen frissíti a leírását.
    op.execute(sa.text("""
        INSERT INTO permissions (code, module, name, description, is_module_access)
        SELECT 'procurement.approve', 'procurement', 'Beszerzési igények jóváhagyása',
               'Beszerzési igények teljes listájának megtekintése, jóváhagyása és elutasítása.', false
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'procurement.approve')
    """))


def downgrade():
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'procurement.approve'"))
    op.drop_table("procurement_attachments")
    op.drop_table("procurement_requests")
    op.drop_table("procurement_request_sequences")
