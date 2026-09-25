"""add CRM core

Revision ID: 0020_crm_core
Revises: 0019_hr_leave_management
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_crm_core"
down_revision = "0019_hr_leave_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("customer_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default="új"),
        sa.Column("estimated_value", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="HUF"),
        sa.Column("probability", sa.Integer(), nullable=True),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_crm_opportunities_customer_id", "crm_opportunities", ["customer_id"])
    op.create_index("ix_crm_opportunities_contact_id", "crm_opportunities", ["contact_id"])
    op.create_index("ix_crm_opportunities_owner_user_id", "crm_opportunities", ["owner_user_id"])
    op.create_index("ix_crm_opportunities_title", "crm_opportunities", ["title"])
    op.create_index("ix_crm_opportunities_stage", "crm_opportunities", ["stage"])
    op.create_index("ix_crm_opportunities_expected_close_date", "crm_opportunities", ["expected_close_date"])
    op.create_index("ix_crm_opportunities_customer_stage", "crm_opportunities", ["customer_id", "stage"])
    op.create_index("ix_crm_opportunities_owner_stage", "crm_opportunities", ["owner_user_id", "stage"])
    op.create_index("ix_crm_opportunities_expected_close", "crm_opportunities", ["expected_close_date"])

    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("customer_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("crm_opportunities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_crm_activities_customer_id", "crm_activities", ["customer_id"])
    op.create_index("ix_crm_activities_contact_id", "crm_activities", ["contact_id"])
    op.create_index("ix_crm_activities_opportunity_id", "crm_activities", ["opportunity_id"])
    op.create_index("ix_crm_activities_work_order_id", "crm_activities", ["work_order_id"])
    op.create_index("ix_crm_activities_owner_user_id", "crm_activities", ["owner_user_id"])
    op.create_index("ix_crm_activities_activity_type", "crm_activities", ["activity_type"])
    op.create_index("ix_crm_activities_due_at", "crm_activities", ["due_at"])
    op.create_index("ix_crm_activities_completed_at", "crm_activities", ["completed_at"])
    op.create_index("ix_crm_activities_created_at", "crm_activities", ["created_at"])
    op.create_index("ix_crm_activities_customer_created", "crm_activities", ["customer_id", "created_at"])
    op.create_index("ix_crm_activities_owner_due", "crm_activities", ["owner_user_id", "due_at"])
    op.create_index("ix_crm_activities_opportunity", "crm_activities", ["opportunity_id"])


def downgrade():
    for index in (
        "ix_crm_activities_opportunity", "ix_crm_activities_owner_due", "ix_crm_activities_customer_created",
        "ix_crm_activities_created_at", "ix_crm_activities_completed_at", "ix_crm_activities_due_at",
        "ix_crm_activities_activity_type", "ix_crm_activities_owner_user_id", "ix_crm_activities_work_order_id",
        "ix_crm_activities_opportunity_id", "ix_crm_activities_contact_id", "ix_crm_activities_customer_id",
    ):
        op.drop_index(index, table_name="crm_activities")
    op.drop_table("crm_activities")

    for index in (
        "ix_crm_opportunities_expected_close", "ix_crm_opportunities_owner_stage", "ix_crm_opportunities_customer_stage",
        "ix_crm_opportunities_expected_close_date", "ix_crm_opportunities_stage", "ix_crm_opportunities_title",
        "ix_crm_opportunities_owner_user_id", "ix_crm_opportunities_contact_id", "ix_crm_opportunities_customer_id",
    ):
        op.drop_index(index, table_name="crm_opportunities")
    op.drop_table("crm_opportunities")
