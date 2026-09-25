"""add modular permission system

Revision ID: 0017_module_permissions
Revises: 0016_work_order_contract_type
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_module_permissions"
down_revision = "0016_work_order_contract_type"
branch_labels = None
depends_on = None


PERMISSIONS = (
    ("service.access", "service", "Szerviz modul", "Hozzáférés a Szerviz modulhoz.", True),
    ("hr.access", "hr", "HR modul", "Hozzáférés a HR modulhoz.", True),
    ("hr.leave.self", "hr", "Saját szabadságadatok", "Saját szabadságadatok megtekintése.", False),
    ("hr.leave.request", "hr", "Szabadságigénylés", "Saját szabadságigény létrehozása.", False),
    ("hr.leave.approve", "hr", "Szabadság jóváhagyása", "Hozzárendelt szabadságigények jóváhagyása.", False),
    ("hr.summary.view", "hr", "HR összesítés megtekintése", "Több munkavállaló HR összesítésének megtekintése.", False),
    ("hr.admin", "hr", "HR adminisztráció", "HR adminisztratív funkciók kezelése.", False),
    ("crm.access", "crm", "CRM modul", "Hozzáférés a CRM modulhoz.", True),
    ("crm.write", "crm", "CRM adatok módosítása", "CRM adatok létrehozása és módosítása.", False),
    ("crm.contract.manage", "crm", "CRM szerződéskezelés", "CRM szerződéskezelési funkciók használata.", False),
    ("crm.admin", "crm", "CRM adminisztráció", "CRM adminisztratív funkciók kezelése.", False),
)


def upgrade():
    permissions = op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_module_access", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)
    op.create_index("ix_permissions_module", "permissions", ["module"], unique=False)

    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.bulk_insert(
        permissions,
        [
            {
                "code": code,
                "module": module,
                "name": name,
                "description": description,
                "is_module_access": is_module_access,
            }
            for code, module, name, description, is_module_access in PERMISSIONS
        ],
    )

    # Frissítéskor minden meglévő felhasználó megtartja az eddigi Szerviz
    # hozzáférését. HR/CRM hozzáférést csak admin adhat később.
    op.execute(
        sa.text(
            """
            INSERT INTO user_permissions (user_id, permission_id)
            SELECT users.id, permissions.id
            FROM users, permissions
            WHERE permissions.code = 'service.access'
            """
        )
    )


def downgrade():
    op.drop_table("user_permissions")
    op.drop_index("ix_permissions_module", table_name="permissions")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
