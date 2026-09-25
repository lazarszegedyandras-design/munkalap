import pytest

from app.access_control import (
    MODULE_ADMIN,
    MODULE_PROCUREMENT,
    PERMISSION_ADMIN_ACCESS,
    PERMISSION_ADMIN_BACKUP_MANAGE,
    PERMISSION_ADMIN_BACKUP_RESTORE,
    module_codes_for_permissions,
    validate_permission_codes,
)


def test_backup_manage_requires_admin_module_and_grants_admin_module_visibility():
    with pytest.raises(ValueError):
        validate_permission_codes([PERMISSION_ADMIN_BACKUP_MANAGE])
    selected = validate_permission_codes([PERMISSION_ADMIN_ACCESS, PERMISSION_ADMIN_BACKUP_MANAGE])
    assert module_codes_for_permissions(selected) == [MODULE_PROCUREMENT, MODULE_ADMIN]


def test_backup_restore_requires_manage_permission():
    with pytest.raises(ValueError):
        validate_permission_codes([PERMISSION_ADMIN_ACCESS, PERMISSION_ADMIN_BACKUP_RESTORE])
    selected = validate_permission_codes([
        PERMISSION_ADMIN_ACCESS,
        PERMISSION_ADMIN_BACKUP_MANAGE,
        PERMISSION_ADMIN_BACKUP_RESTORE,
    ])
    assert PERMISSION_ADMIN_BACKUP_RESTORE in selected
