"""customer contacts and work order contact

Revision ID: 0003_customer_contacts
Revises: 0002_import_fields
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_customer_contacts"
down_revision = "0002_import_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="Egyéb"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_contacts_customer_id", "customer_contacts", ["customer_id"])
    op.create_index("ix_customer_contacts_location_id", "customer_contacts", ["location_id"])
    op.create_index("ix_customer_contacts_category", "customer_contacts", ["category"])

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("contact_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_work_orders_contact_id", "customer_contacts", ["contact_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_work_orders_contact_id", ["contact_id"])

    op.execute(
        """
        INSERT INTO customer_contacts (customer_id, category, name, phone, email, is_primary, created_at)
        SELECT id, 'Szerviz', contact_person, phone, email, TRUE, CURRENT_TIMESTAMP
        FROM customers
        WHERE contact_person IS NOT NULL AND trim(contact_person) <> ''
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_index("ix_work_orders_contact_id")
        batch_op.drop_constraint("fk_work_orders_contact_id", type_="foreignkey")
        batch_op.drop_column("contact_id")
    op.drop_index("ix_customer_contacts_category", table_name="customer_contacts")
    op.drop_index("ix_customer_contacts_location_id", table_name="customer_contacts")
    op.drop_index("ix_customer_contacts_customer_id", table_name="customer_contacts")
    op.drop_table("customer_contacts")
