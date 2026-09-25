"""add forced password change flag

Revision ID: 0014_user_password_policy
Revises: 0013_meter_channels
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_user_password_policy"
down_revision = "0013_meter_channels"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("users", "must_change_password")
