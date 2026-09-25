"""Add race-safe work order numbering and optimistic locking.

Revision ID: 0006_work_order_concurrency
Revises: 0005_work_order_type
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_work_order_concurrency"
down_revision = "0005_work_order_type"
branch_labels = None
depends_on = None

SEQUENCE_NAME = "work_order_number_seq"


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE_NAME} START WITH 1 INCREMENT BY 1"))
        op.execute(
            sa.text(
                f"""
                SELECT setval(
                    '{SEQUENCE_NAME}',
                    GREATEST(
                        COALESCE(
                            (
                                SELECT MAX((substring(number from '([0-9]+)$'))::bigint)
                                FROM work_orders
                                WHERE number ~ '[0-9]+$'
                            ),
                            0
                        ) + 1,
                        1
                    ),
                    false
                )
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {SEQUENCE_NAME}"))
    op.drop_column("work_orders", "version")
