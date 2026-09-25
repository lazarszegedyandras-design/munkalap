"""cloud security foundation: sessions, MFA and login throttling

Revision ID: 0029_cloud_security
Revises: 0028_procurement
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_cloud_security"
down_revision = "0028_procurement"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True))
        batch.add_column(sa.Column("mfa_recovery_codes", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("mfa_last_counter", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("mfa_enrolled_at", sa.DateTime(), nullable=True))

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("absolute_expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("mfa_verified_at", sa.DateTime(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_auth_sessions_session_id", "auth_sessions", ["session_id"], unique=True)
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_user_revoked", "auth_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_auth_sessions_absolute_expires", "auth_sessions", ["absolute_expires_at"])

    op.create_table(
        "security_rate_limits",
        sa.Column("bucket_key", sa.String(length=96), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("blocked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_security_rate_limits_blocked_until", "security_rate_limits", ["blocked_until"])


def downgrade():
    op.drop_table("security_rate_limits")
    op.drop_table("auth_sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mfa_enrolled_at")
        batch.drop_column("mfa_last_counter")
        batch.drop_column("mfa_recovery_codes")
        batch.drop_column("mfa_secret_encrypted")
        batch.drop_column("mfa_enabled")
