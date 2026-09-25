"""Add work order edit presence sessions.

Revision ID: 0007_work_order_edit_presence
Revises: 0006_work_order_concurrency
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_work_order_edit_presence"
down_revision = "0006_work_order_concurrency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_order_edit_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_token", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_token", name="uq_work_order_edit_session_token"),
    )
    op.create_index("ix_work_order_edit_sessions_work_order_id", "work_order_edit_sessions", ["work_order_id"])
    op.create_index("ix_work_order_edit_sessions_user_id", "work_order_edit_sessions", ["user_id"])
    op.create_index("ix_work_order_edit_sessions_last_seen_at", "work_order_edit_sessions", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_work_order_edit_sessions_last_seen_at", table_name="work_order_edit_sessions")
    op.drop_index("ix_work_order_edit_sessions_user_id", table_name="work_order_edit_sessions")
    op.drop_index("ix_work_order_edit_sessions_work_order_id", table_name="work_order_edit_sessions")
    op.drop_table("work_order_edit_sessions")
