"""add active status to customer locations

Revision ID: 0026_location_active_status
Revises: 0025_admin_backup_permissions
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0026_location_active_status"
down_revision = "0025_admin_backup_permissions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("locations") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.create_index("ix_locations_is_active", ["is_active"])


def downgrade():
    with op.batch_alter_table("locations") as batch:
        batch.drop_index("ix_locations_is_active")
        batch.drop_column("is_active")
