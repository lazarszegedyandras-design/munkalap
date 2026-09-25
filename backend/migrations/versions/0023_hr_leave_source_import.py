"""extend HR leave model and stage supplied 2026 source data

Revision ID: 0023_hr_leave_source_import
Revises: 0022_notifications_reports
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_hr_leave_source_import"
down_revision = "0022_notifications_reports"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("employee_profiles") as batch:
        batch.add_column(sa.Column("job_title", sa.String(length=255), nullable=True))

    with op.batch_alter_table("leave_entitlements") as batch:
        batch.add_column(sa.Column("child_days", sa.Numeric(6, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("sick_leave_days", sa.Numeric(6, 2), nullable=False, server_default="0"))

    with op.batch_alter_table("leave_requests") as batch:
        batch.alter_column("approver_user_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("leave_type", sa.String(length=32), nullable=False, server_default="annual_leave"))
        batch.add_column(sa.Column("source", sa.String(length=64), nullable=False, server_default="workflow"))
        batch.add_column(sa.Column("source_reference", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_record_date", sa.Date(), nullable=True))
        batch.create_unique_constraint("uq_leave_requests_source_reference", ["source_reference"])
        batch.create_index("ix_leave_requests_leave_type", ["leave_type"])
        batch.create_index("ix_leave_requests_source", ["source"])
        batch.create_index("ix_leave_requests_source_reference", ["source_reference"])

    op.create_table(
        "hr_leave_import_people",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email_hint", sa.String(length=255), nullable=True),
        sa.Column("employee_number", sa.String(length=100), nullable=False),
        sa.Column("employment_start_date", sa.Date(), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("base_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("child_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("sick_leave_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_record_date", sa.Date(), nullable=True),
        sa.Column("linked_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_key", name="uq_hr_leave_import_people_source_key"),
    )
    op.create_index("ix_hr_leave_import_people_year", "hr_leave_import_people", ["year"])
    op.create_index("ix_hr_leave_import_people_status", "hr_leave_import_people", ["status"])
    op.create_index("ix_hr_leave_import_people_linked_user_id", "hr_leave_import_people", ["linked_user_id"])

    op.create_table(
        "hr_leave_import_absences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_person_id", sa.Integer(), sa.ForeignKey("hr_leave_import_people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("leave_type", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Numeric(6, 2), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("source_reference", name="uq_hr_leave_import_absences_source_reference"),
    )
    op.create_index("ix_hr_leave_import_absences_import_person_id", "hr_leave_import_absences", ["import_person_id"])
    op.create_index("ix_hr_leave_import_absences_dates", "hr_leave_import_absences", ["start_date", "end_date"])


def downgrade():
    op.drop_table("hr_leave_import_absences")
    op.drop_table("hr_leave_import_people")

    # Historical imported rows may have no approver and cannot fit the old schema.
    op.execute("DELETE FROM leave_requests WHERE approver_user_id IS NULL")
    with op.batch_alter_table("leave_requests") as batch:
        batch.drop_index("ix_leave_requests_source_reference")
        batch.drop_index("ix_leave_requests_source")
        batch.drop_index("ix_leave_requests_leave_type")
        batch.drop_constraint("uq_leave_requests_source_reference", type_="unique")
        batch.drop_column("source_record_date")
        batch.drop_column("source_reference")
        batch.drop_column("source")
        batch.drop_column("leave_type")
        batch.alter_column("approver_user_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("leave_entitlements") as batch:
        batch.drop_column("sick_leave_days")
        batch.drop_column("child_days")

    with op.batch_alter_table("employee_profiles") as batch:
        batch.drop_column("job_title")
