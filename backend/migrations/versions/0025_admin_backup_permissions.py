"""add admin backup permissions

Revision ID: 0025_admin_backup_permissions
Revises: 0024_contract_archives_hrcal
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_admin_backup_permissions"
down_revision = "0024_contract_archives_hrcal"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("admin.access", "admin", "Admin modul", "Hozzáférés az engedélyezett adminisztratív funkciókhoz.", True),
    ("admin.backup.manage", "admin", "Biztonsági mentések kezelése", "Mentési pontok, ütemezés, manuális MASTER mentés és integritásellenőrzés kezelése.", False),
    ("admin.backup.restore", "admin", "Biztonsági mentés visszaállítása", "Rendszerszintű visszaállítás indítása.", False),
)


def upgrade():
    permissions = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("module", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_module_access", sa.Boolean),
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


def downgrade():
    op.execute(
        sa.text(
            "DELETE FROM user_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code IN ('admin.access','admin.backup.manage','admin.backup.restore'))"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE code IN ('admin.access','admin.backup.manage','admin.backup.restore')"
        )
    )
