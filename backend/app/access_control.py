from __future__ import annotations

MODULE_SERVICE = "service"
MODULE_HR = "hr"
MODULE_CRM = "crm"
MODULE_ADMIN = "admin"
MODULE_PROCUREMENT = "procurement"

PERMISSION_SERVICE_ACCESS = "service.access"
PERMISSION_HR_ACCESS = "hr.access"
PERMISSION_HR_LEAVE_SELF = "hr.leave.self"
PERMISSION_HR_LEAVE_REQUEST = "hr.leave.request"
PERMISSION_HR_LEAVE_APPROVE = "hr.leave.approve"
PERMISSION_HR_SUMMARY_VIEW = "hr.summary.view"
PERMISSION_HR_ADMIN = "hr.admin"
PERMISSION_CRM_ACCESS = "crm.access"
PERMISSION_CRM_WRITE = "crm.write"
PERMISSION_CRM_CONTRACT_MANAGE = "crm.contract.manage"
PERMISSION_CRM_ADMIN = "crm.admin"
PERMISSION_ADMIN_ACCESS = "admin.access"
PERMISSION_ADMIN_BACKUP_MANAGE = "admin.backup.manage"
PERMISSION_ADMIN_BACKUP_RESTORE = "admin.backup.restore"
PERMISSION_PROCUREMENT_APPROVE = "procurement.approve"

PERMISSION_CATALOG = (
    {
        "code": PERMISSION_SERVICE_ACCESS,
        "module": MODULE_SERVICE,
        "name": "Szerviz modul",
        "description": "Hozzáférés a munkalap-, eszköz-, ügyfél- és anyagkezelési Szerviz modulhoz.",
        "is_module_access": True,
    },
    {
        "code": PERMISSION_HR_ACCESS,
        "module": MODULE_HR,
        "name": "HR modul",
        "description": "Hozzáférés a HR modulhoz. A részletes HR funkciók külön jogosultsághoz köthetők.",
        "is_module_access": True,
    },
    {
        "code": PERMISSION_HR_LEAVE_SELF,
        "module": MODULE_HR,
        "name": "Saját szabadságadatok",
        "description": "A saját szabadságkeret és saját szabadságigények megtekintése.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_HR_LEAVE_REQUEST,
        "module": MODULE_HR,
        "name": "Szabadságigénylés",
        "description": "Saját szabadságigény létrehozása és beküldése.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_HR_LEAVE_APPROVE,
        "module": MODULE_HR,
        "name": "Szabadság jóváhagyása",
        "description": "A felhasználóhoz rendelt szabadságigények vezetői jóváhagyása vagy elutasítása.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_HR_SUMMARY_VIEW,
        "module": MODULE_HR,
        "name": "HR összesítés megtekintése",
        "description": "A több munkavállalót tartalmazó HR szabadság-összesítés megtekintése.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_HR_ADMIN,
        "module": MODULE_HR,
        "name": "HR adminisztráció",
        "description": "HR törzsadatok és későbbi HR adminisztrációs funkciók kezelése.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_CRM_ACCESS,
        "module": MODULE_CRM,
        "name": "CRM modul",
        "description": "Hozzáférés a CRM modulhoz.",
        "is_module_access": True,
    },
    {
        "code": PERMISSION_CRM_WRITE,
        "module": MODULE_CRM,
        "name": "CRM adatok módosítása",
        "description": "CRM aktivitások, lehetőségek és kapcsolódó adatok létrehozása/módosítása.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_CRM_CONTRACT_MANAGE,
        "module": MODULE_CRM,
        "name": "CRM szerződéskezelés",
        "description": "CRM szerződések, telephely- és eszközhatály kezelésének használata.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_CRM_ADMIN,
        "module": MODULE_CRM,
        "name": "CRM adminisztráció",
        "description": "CRM beállítások és adminisztratív funkciók kezelése.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_PROCUREMENT_APPROVE,
        "module": MODULE_PROCUREMENT,
        "name": "Beszerzési igények jóváhagyása",
        "description": "Beszerzési igények teljes listájának megtekintése, jóváhagyása és elutasítása.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_ADMIN_ACCESS,
        "module": MODULE_ADMIN,
        "name": "Admin modul",
        "description": "Hozzáférés az engedélyezett adminisztratív funkciókhoz.",
        "is_module_access": True,
    },
    {
        "code": PERMISSION_ADMIN_BACKUP_MANAGE,
        "module": MODULE_ADMIN,
        "name": "Biztonsági mentések kezelése",
        "description": "Mentési pontok, ütemezés, manuális MASTER mentés és integritásellenőrzés kezelése.",
        "is_module_access": False,
    },
    {
        "code": PERMISSION_ADMIN_BACKUP_RESTORE,
        "module": MODULE_ADMIN,
        "name": "Biztonsági mentés visszaállítása",
        "description": "Rendszerszintű visszaállítás indítása. A mentéskezelési jogosultság is szükséges.",
        "is_module_access": False,
    },
)

VALID_PERMISSION_CODES = frozenset(item["code"] for item in PERMISSION_CATALOG)
MODULE_ACCESS_PERMISSIONS = {
    MODULE_SERVICE: PERMISSION_SERVICE_ACCESS,
    MODULE_HR: PERMISSION_HR_ACCESS,
    MODULE_CRM: PERMISSION_CRM_ACCESS,
    MODULE_ADMIN: PERMISSION_ADMIN_ACCESS,
}


def validate_permission_codes(codes: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    normalized = sorted({str(code).strip() for code in (codes or []) if str(code).strip()})
    unknown = sorted(set(normalized) - VALID_PERMISSION_CODES)
    if unknown:
        raise ValueError("Ismeretlen jogosultság: " + ", ".join(unknown))

    selected = set(normalized)
    if PERMISSION_HR_LEAVE_REQUEST in selected and PERMISSION_HR_LEAVE_SELF not in selected:
        raise ValueError(f"A(z) {PERMISSION_HR_LEAVE_REQUEST} jogosultsághoz a(z) {PERMISSION_HR_LEAVE_SELF} jogosultság is szükséges")
    if PERMISSION_ADMIN_BACKUP_RESTORE in selected and PERMISSION_ADMIN_BACKUP_MANAGE not in selected:
        raise ValueError(
            f"A(z) {PERMISSION_ADMIN_BACKUP_RESTORE} jogosultsághoz a(z) {PERMISSION_ADMIN_BACKUP_MANAGE} jogosultság is szükséges"
        )
    for item in PERMISSION_CATALOG:
        code = item["code"]
        if code not in selected or item["is_module_access"]:
            continue
        module_access = MODULE_ACCESS_PERMISSIONS.get(item["module"])
        if module_access and module_access not in selected:
            raise ValueError(
                f"A(z) {code} jogosultsághoz a(z) {module_access} modul-hozzáférés is szükséges"
            )
    return normalized


def module_codes_for_permissions(codes: list[str] | set[str] | tuple[str, ...], *, is_admin: bool = False) -> list[str]:
    selected = set(codes)
    enabled = {module for module, permission in MODULE_ACCESS_PERMISSIONS.items() if permission in selected}
    # A Beszerzés modul minden aktív, bejelentkezésre jogosult felhasználó számára elérhető.
    enabled.add(MODULE_PROCUREMENT)
    if is_admin:
        enabled.update((MODULE_SERVICE, MODULE_HR, MODULE_CRM, MODULE_ADMIN))
    return [
        module
        for module in (MODULE_SERVICE, MODULE_HR, MODULE_CRM, MODULE_PROCUREMENT, MODULE_ADMIN)
        if module in enabled
    ]
