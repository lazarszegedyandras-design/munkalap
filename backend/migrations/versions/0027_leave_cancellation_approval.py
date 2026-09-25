"""add approval workflow for leave cancellation

Revision ID: 0027_leave_cancel_approval
Revises: 0026_location_active_status
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0027_leave_cancel_approval"
down_revision = "0026_location_active_status"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("leave_requests") as batch:
        batch.add_column(sa.Column("cancellation_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("cancellation_approver_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("cancellation_comment", sa.Text(), nullable=True))
        batch.add_column(sa.Column("cancellation_approver_comment", sa.Text(), nullable=True))
        batch.add_column(sa.Column("cancellation_requested_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cancellation_decided_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_leave_requests_cancellation_approver",
            "users",
            ["cancellation_approver_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_leave_requests_cancellation_status", ["cancellation_status"])
        batch.create_index("ix_leave_requests_cancellation_approver_user_id", ["cancellation_approver_user_id"])


def downgrade():
    with op.batch_alter_table("leave_requests") as batch:
        batch.drop_index("ix_leave_requests_cancellation_approver_user_id")
        batch.drop_index("ix_leave_requests_cancellation_status")
        batch.drop_constraint("fk_leave_requests_cancellation_approver", type_="foreignkey")
        batch.drop_column("cancellation_decided_at")
        batch.drop_column("cancellation_requested_at")
        batch.drop_column("cancellation_approver_comment")
        batch.drop_column("cancellation_comment")
        batch.drop_column("cancellation_approver_user_id")
        batch.drop_column("cancellation_status")
