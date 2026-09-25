"""add HR leave management

Revision ID: 0019_hr_leave_management
Revises: 0018_structured_audit_log
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_hr_leave_management"
down_revision = "0018_structured_audit_log"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employee_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("employee_number", sa.String(length=100), nullable=True),
        sa.Column("company_code", sa.String(length=50), nullable=True),
        sa.Column("organizational_unit", sa.String(length=255), nullable=True),
        sa.Column("manager_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("leave_approver_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employment_start_date", sa.Date(), nullable=True),
        sa.Column("employment_end_date", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", name="uq_employee_profiles_user_id"),
        sa.UniqueConstraint("employee_number", name="uq_employee_profiles_employee_number"),
    )
    op.create_index("ix_employee_profiles_user_id", "employee_profiles", ["user_id"])
    op.create_index("ix_employee_profiles_active", "employee_profiles", ["active"])
    op.create_index("ix_employee_profiles_company_code", "employee_profiles", ["company_code"])
    op.create_index("ix_employee_profiles_organizational_unit", "employee_profiles", ["organizational_unit"])
    op.create_index("ix_employee_profiles_manager_user_id", "employee_profiles", ["manager_user_id"])
    op.create_index("ix_employee_profiles_leave_approver", "employee_profiles", ["leave_approver_user_id"])

    op.create_table(
        "leave_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("base_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("carried_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("employee_id", "year", name="uq_leave_entitlements_employee_year"),
    )
    op.create_index("ix_leave_entitlements_employee_id", "leave_entitlements", ["employee_id"])
    op.create_index("ix_leave_entitlements_year", "leave_entitlements", ["year"])

    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approver_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("requested_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("employee_comment", sa.Text(), nullable=True),
        sa.Column("approver_comment", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_leave_requests_employee_id", "leave_requests", ["employee_id"])
    op.create_index("ix_leave_requests_approver_user_id", "leave_requests", ["approver_user_id"])
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])
    op.create_index("ix_leave_requests_employee_status", "leave_requests", ["employee_id", "status"])
    op.create_index("ix_leave_requests_approver_status", "leave_requests", ["approver_user_id", "status"])
    op.create_index("ix_leave_requests_dates", "leave_requests", ["start_date", "end_date"])

    op.create_table(
        "work_calendar_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calendar_date", sa.Date(), nullable=False, unique=True),
        sa.Column("is_working_day", sa.Boolean(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_work_calendar_days_calendar_date", "work_calendar_days", ["calendar_date"], unique=True)


def downgrade():
    op.drop_index("ix_work_calendar_days_calendar_date", table_name="work_calendar_days")
    op.drop_table("work_calendar_days")

    op.drop_index("ix_leave_requests_dates", table_name="leave_requests")
    op.drop_index("ix_leave_requests_approver_status", table_name="leave_requests")
    op.drop_index("ix_leave_requests_employee_status", table_name="leave_requests")
    op.drop_index("ix_leave_requests_status", table_name="leave_requests")
    op.drop_index("ix_leave_requests_approver_user_id", table_name="leave_requests")
    op.drop_index("ix_leave_requests_employee_id", table_name="leave_requests")
    op.drop_table("leave_requests")

    op.drop_index("ix_leave_entitlements_year", table_name="leave_entitlements")
    op.drop_index("ix_leave_entitlements_employee_id", table_name="leave_entitlements")
    op.drop_table("leave_entitlements")

    op.drop_index("ix_employee_profiles_leave_approver", table_name="employee_profiles")
    op.drop_index("ix_employee_profiles_manager_user_id", table_name="employee_profiles")
    op.drop_index("ix_employee_profiles_organizational_unit", table_name="employee_profiles")
    op.drop_index("ix_employee_profiles_company_code", table_name="employee_profiles")
    op.drop_index("ix_employee_profiles_active", table_name="employee_profiles")
    op.drop_index("ix_employee_profiles_user_id", table_name="employee_profiles")
    op.drop_table("employee_profiles")
