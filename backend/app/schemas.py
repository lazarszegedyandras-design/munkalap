from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

AssetStatus = Literal["aktív", "hibás", "javítás alatt", "selejtezett", "raktáron"]
WorkOrderStatus = Literal["új", "ütemezve", "folyamatban", "várakozik", "kész", "lezárva", "törölve / sztornózva"]
Priority = Literal["alacsony", "normál", "sürgős"]
WorkType = Literal["karbantartás", "javítás", "eseti javítás", "kiszállítás", "üzembe helyezés"]
ContactCategory = Literal["Szerviz", "Sales", "Egyéb"]
RoleName = Literal["Admin", "Irodai felhasználó", "Technikus / szerelő"]


class Token(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_setup_required: bool = False
    challenge_token: str | None = None


class MobileDeviceInfo(BaseModel):
    device_uuid: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    device_name: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="android", min_length=1, max_length=32)
    app_version: str | None = Field(default=None, max_length=64)


class MobileLoginRequest(MobileDeviceInfo):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MobileMfaVerifyRequest(MobileDeviceInfo):
    challenge_token: str = Field(min_length=20, max_length=4096)
    code: str = Field(min_length=6, max_length=32)


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=512)


class MobileAuthRead(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_expires_at: datetime | None = None
    device_id: int | None = None
    mfa_required: bool = False
    mfa_setup_required: bool = False
    challenge_token: str | None = None


class MobileDeviceRead(BaseModel):
    id: int
    device_uuid: str
    device_name: str
    platform: str
    app_version: str | None = None
    push_enabled: bool = False
    push_token_updated_at: datetime | None = None
    last_seen_at: datetime
    revoked_at: datetime | None = None


class MobilePushTokenUpdate(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    enabled: bool = True


class MobileWorkOrderMaterialInput(BaseModel):
    material_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)


class MobileWorkOrderStart(BaseModel):
    version: int = Field(ge=1)
    started_at: datetime | None = None


class MobileWorkOrderComplete(BaseModel):
    version: int = Field(ge=1)
    work_done: str = Field(min_length=1, max_length=20000)
    final_status: str | None = Field(default=None, max_length=255)
    labor_hours: Decimal | None = Field(default=None, ge=0, le=24)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    internal_note: str | None = Field(default=None, max_length=20000)
    customer_note: str | None = Field(default=None, max_length=20000)
    materials: list[MobileWorkOrderMaterialInput] | None = None


class MobileMeterReadingCreate(BaseModel):
    asset_id: int
    value: int = Field(ge=0)
    black_white_value: int | None = Field(default=None, ge=0)
    color_value: int | None = Field(default=None, ge=0)
    scan_value: int | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)




class MobileWorkOrderPhotoRead(BaseModel):
    id: int
    work_order_id: int
    category: str
    note: str | None = None
    original_filename: str | None = None
    sha256: str
    size_bytes: int
    mime_type: str
    width: int
    height: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MobileSignatureRead(BaseModel):
    id: int
    snapshot_id: int
    signer_name: str
    signer_role: str | None = None
    signed_at: datetime
    signature_sha256: str
    signed_pdf_sha256: str
    signed_pdf_size_bytes: int


class MobileCompletionSnapshotRead(BaseModel):
    id: int
    work_order_id: int
    revision: int
    source_work_order_version: int
    snapshot_sha256: str
    snapshot: dict
    created_at: datetime
    signature: MobileSignatureRead | None = None


class MfaChallengeRequest(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=4096)


class MfaVerifyRequest(MfaChallengeRequest):
    code: str = Field(min_length=6, max_length=32)


class MfaSetupRead(BaseModel):
    secret: str
    otpauth_uri: str


class MfaConfirmRead(Token):
    recovery_codes: list[str] = Field(default_factory=list)


class MfaStatusRead(BaseModel):
    enabled: bool
    required: bool
    recovery_codes_remaining: int = 0


class MfaStepUpRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaStepUpRead(BaseModel):
    ok: bool = True
    verified_at: datetime


class RoleRead(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class PermissionRead(BaseModel):
    code: str
    module: str
    name: str
    description: str | None = None
    is_module_access: bool = False


class PermissionAssignmentUpdate(BaseModel):
    permission_codes: list[str] = Field(default_factory=list)


class BackupScheduleUpdate(BaseModel):
    enabled: bool = False
    daily_time: str = Field(default="23:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Europe/Budapest", max_length=100)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str):
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("Érvénytelen időzóna") from exc
        return value




class BackupRestoreRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str):
        if value != "VISSZAALLIT":
            raise ValueError("A visszaállításhoz pontosan ezt kell megadni: VISSZAALLIT")
        return value


class BackupRecoveryClearRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str):
        if value != "HELYREALLITAS_KESZ":
            raise ValueError("A zárolás feloldásához pontosan ezt kell megadni: HELYREALLITAS_KESZ")
        return value


class BackupRestoreEvent(BaseModel):
    restore_id: str = Field(min_length=1, max_length=100)
    backup_id: str = Field(min_length=1, max_length=100)
    pre_restore_backup_id: str | None = Field(default=None, max_length=100)
    post_restore_backup_id: str | None = Field(default=None, max_length=100)
    rollback_restore_backup_id: str | None = Field(default=None, max_length=100)
    requested_by_user_id: int | None = None
    requested_by_name: str | None = Field(default=None, max_length=255)
    requested_by_email: EmailStr | None = None
    outcome: Literal["success", "failed_rolled_back"]
    checks: dict = Field(default_factory=dict)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    is_active: bool = True
    role_id: int


class PasswordPolicyMixin:
    @field_validator("password", "new_password", check_fields=False)
    @classmethod
    def validate_password_strength(cls, value: str | None):
        if value is None:
            return value
        from .passwords import validate_password_policy
        return validate_password_policy(value)


class UserCreate(UserBase, PasswordPolicyMixin):
    password: str = Field(min_length=8, max_length=128)
    permission_codes: list[str] | None = None


class UserUpdate(BaseModel, PasswordPolicyMixin):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    is_active: bool | None = None
    role_id: int | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    permission_codes: list[str] | None = None


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool
    role: RoleRead
    created_at: datetime
    must_change_password: bool
    mfa_enabled: bool = False
    permissions: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class TechnicianCreate(BaseModel, PasswordPolicyMixin):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class TechnicianUpdate(BaseModel, PasswordPolicyMixin):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel, PasswordPolicyMixin):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)




class CompanyProfileUpdate(BaseModel):
    aliases: list[str] | None = None
    short_name: str | None = Field(default=None, max_length=255)
    legal_name: str | None = Field(default=None, max_length=500)
    tax_number: str | None = Field(default=None, max_length=64)
    company_registration_number: str | None = Field(default=None, max_length=64)
    registered_address: str | None = Field(default=None, max_length=500)
    contact_address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=64)
    mobile_phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    worksheet_phone: str | None = Field(default=None, max_length=128)
    worksheet_email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    contact_person: str | None = Field(default=None, max_length=255)
    activity: str | None = Field(default=None, max_length=500)
    source_note: str | None = None


class LocationBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str | None = None
    gps_lat: str | None = None
    gps_lng: str | None = None
    note: str | None = None


class LocationCreate(LocationBase):
    customer_id: int | None = None


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    gps_lat: str | None = None
    gps_lng: str | None = None
    note: str | None = None
    is_active: bool = True


class LocationRead(LocationBase):
    id: int
    customer_id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class CustomerContactBase(BaseModel):
    category: ContactCategory = "Egyéb"
    name: str = Field(min_length=1, max_length=255)
    title: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    location_id: int | None = None
    note: str | None = None
    is_primary: bool = False


class CustomerContactCreate(CustomerContactBase):
    pass


class CustomerContactUpdate(BaseModel):
    category: ContactCategory | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    location_id: int | None = None
    note: str | None = None
    is_primary: bool | None = None


class CustomerContactRead(CustomerContactBase):
    id: int
    customer_id: int
    location_name: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    note: str | None = None
    company_code: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    note: str | None = None
    company_code: str | None = None


class CustomerRead(CustomerBase):
    id: int
    created_at: datetime
    locations: list[LocationRead] = Field(default_factory=list)
    contacts: list[CustomerContactRead] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class AssetBase(BaseModel):
    internal_id: str = Field(min_length=1, max_length=100)
    serial_number: str | None = None
    type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    category: str | None = None
    status: AssetStatus = "aktív"
    current_location_id: int | None = None
    customer_id: int | None = None
    internal_use: bool = False
    purchase_date: date | None = None
    warranty_expiry: date | None = None
    last_maintenance_date: date | None = None
    maintenance_cycle_months: int | None = Field(default=None, ge=1, le=120)
    maintenance_cycle_note: str | None = Field(default=None, max_length=255)
    next_maintenance_date: date | None = None
    note: str | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    internal_id: str | None = Field(default=None, min_length=1, max_length=100)
    serial_number: str | None = None
    type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    category: str | None = None
    status: AssetStatus | None = None
    current_location_id: int | None = None
    customer_id: int | None = None
    internal_use: bool | None = None
    purchase_date: date | None = None
    warranty_expiry: date | None = None
    last_maintenance_date: date | None = None
    maintenance_cycle_months: int | None = Field(default=None, ge=1, le=120)
    maintenance_cycle_note: str | None = Field(default=None, max_length=255)
    next_maintenance_date: date | None = None
    note: str | None = None


class AssetRead(AssetBase):
    id: int
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    location_name: str | None = None
    company_code: str | None = None
    import_source: str | None = None
    import_batch: str | None = None
    import_row: int | None = None
    display_internal_id: str | None = None
    internal_id_hidden: bool = False
    display_name: str | None = None
    latest_meter_value: int | None = None
    latest_meter_at: datetime | None = None
    meter_age_days: int | None = None
    meter_state: str | None = None
    meter_state_label: str | None = None
    average_monthly_usage: float | None = None
    next_component_name: str | None = None
    next_component_forecast_at: datetime | None = None
    component_forecast_status: str | None = None
    component_forecast_status_label: str | None = None
    component_due_count: int = 0
    maintenance_state: str | None = None
    maintenance_state_label: str | None = None
    maintenance_cycle_label: str | None = None
    calculated_next_maintenance_date: date | None = None
    effective_next_maintenance_date: date | None = None
    maintenance_due_source: str | None = None
    maintenance_days_since_last: int | None = None
    maintenance_days_until_due: int | None = None


class AssetListSummary(BaseModel):
    total: int = 0
    active: int = 0
    problem: int = 0
    maintenance: int = 0
    maintenance_missing: int = 0
    component_due: int = 0
    stale_meters: int = 0


class AssetPage(BaseModel):
    items: list[AssetRead] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    pages: int
    sort: str
    order: Literal["asc", "desc"]
    summary: AssetListSummary


class AssetHistoryRead(BaseModel):
    id: int
    asset_id: int
    action: str
    description: str
    changed_at: datetime
    user_name: str | None = None
    work_order_number: str | None = None


class MaterialBase(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(default="db", min_length=1, max_length=32)
    unit_price: Decimal | None = None
    stock: Decimal | None = None
    note: str | None = None


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    unit_price: Decimal | None = None
    stock: Decimal | None = None
    note: str | None = None


class MaterialRead(MaterialBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class WorkOrderMaterialInput(BaseModel):
    material_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = None
    note: str | None = None


class WorkOrderBase(BaseModel):
    customer_id: int
    location_id: int | None = None
    contact_id: int | None = None
    contract_id: int | None = None
    asset_ids: list[int] = Field(default_factory=list)
    description: str = Field(min_length=1)
    priority: Priority = "normál"
    technician_id: int | None = None
    secondary_technician_id: int | None = None
    planned_date: date | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    work_done: str | None = None
    labor_hours: Decimal | None = None
    work_type: WorkType | None = None
    contract_type: str | None = Field(default=None, max_length=120)
    internal_note: str | None = None
    customer_note: str | None = None
    materials: list[WorkOrderMaterialInput] = Field(default_factory=list)


class WorkOrderCreate(WorkOrderBase):
    status: WorkOrderStatus = "új"


class BulkMaintenanceSkippedAsset(BaseModel):
    asset_id: int
    display_name: str
    reason: str


class BulkMaintenanceWorkOrdersResult(BaseModel):
    customer_id: int
    total_assets: int
    created_count: int
    skipped_count: int
    created_work_order_ids: list[int] = Field(default_factory=list)
    skipped_assets: list[BulkMaintenanceSkippedAsset] = Field(default_factory=list)


class BulkWorkOrderVersion(BaseModel):
    id: int = Field(gt=0)
    version: int = Field(ge=1)


class BulkWorkOrderUpdate(BaseModel):
    items: list[BulkWorkOrderVersion] = Field(min_length=1, max_length=500)
    apply_status: bool = False
    status: WorkOrderStatus | None = None
    apply_planned_date: bool = False
    planned_date: date | None = None
    apply_technician: bool = False
    technician_id: int | None = None
    apply_secondary_technician: bool = False
    secondary_technician_id: int | None = None


class BulkWorkOrderUpdateResult(BaseModel):
    updated_count: int
    updated_work_order_ids: list[int] = Field(default_factory=list)


class WorkOrderUpdate(BaseModel):
    version: int = Field(ge=1)
    customer_id: int | None = None
    location_id: int | None = None
    contact_id: int | None = None
    contract_id: int | None = None
    asset_ids: list[int] | None = None
    description: str | None = Field(default=None, min_length=1)
    status: WorkOrderStatus | None = None
    priority: Priority | None = None
    technician_id: int | None = None
    secondary_technician_id: int | None = None
    planned_date: date | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    work_done: str | None = None
    labor_hours: Decimal | None = None
    work_type: WorkType | None = None
    contract_type: str | None = Field(default=None, max_length=120)
    internal_note: str | None = None
    customer_note: str | None = None
    materials: list[WorkOrderMaterialInput] | None = None


class WorkOrderPage(BaseModel):
    items: list[dict] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    pages: int
    sort: str
    order: Literal["asc", "desc"]


class WorkOrderSavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: dict = Field(default_factory=dict)
    is_default: bool = False


class WorkOrderSavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    state: dict | None = None
    is_default: bool | None = None


class WorkOrderSavedViewRead(BaseModel):
    id: int
    name: str
    state: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WorkOrderEditHeartbeat(BaseModel):
    session_token: str = Field(min_length=16, max_length=64)


class WorkOrderClose(BaseModel):
    version: int = Field(ge=1)
    work_done: str = Field(min_length=1)
    final_status: str = Field(min_length=1)
    labor_hours: Decimal = Field(ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    technician_id: int | None = None
    secondary_technician_id: int | None = None


class AuditLogRead(BaseModel):
    id: int
    actor_user_id: int | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    entity_type: str
    entity_id: str
    entity_display_id: str | None = None
    description: str
    before_data: dict | None = None
    after_data: dict | None = None
    changes: dict | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    session_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    result: str
    severity: str
    previous_hash: str | None = None
    entry_hash: str
    created_at: datetime


class AssetMeterReadingCreate(BaseModel):
    value: int = Field(ge=0)
    black_white_value: int | None = Field(default=None, ge=0)
    color_value: int | None = Field(default=None, ge=0)
    scan_value: int | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None
    work_order_id: int | None = None
    note: str | None = None


class AssetComponentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    part_number: str | None = Field(default=None, max_length=150)
    expected_life_pages: int | None = Field(default=None, gt=0)
    last_replacement_at: datetime | None = None
    last_replacement_meter: int | None = Field(default=None, ge=0)
    is_active: bool = True
    note: str | None = None


class AssetComponentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    part_number: str | None = Field(default=None, max_length=150)
    expected_life_pages: int | None = Field(default=None, gt=0)
    last_replacement_at: datetime | None = None
    last_replacement_meter: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    note: str | None = None


class AssetComponentReplacementCreate(BaseModel):
    asset_component_id: int
    meter_value: int = Field(ge=0)
    replaced_at: datetime | None = None
    material_id: int | None = None
    work_order_id: int | None = None
    note: str | None = None


# HR / szabadságkezelés
LeaveRequestStatus = Literal["pending", "approved", "rejected", "cancelled"]
LeaveCancellationStatus = Literal["pending", "approved", "rejected"]
LeaveApprovalKind = Literal["leave_request", "cancellation"]
LeaveType = Literal["annual_leave", "sick_leave"]


class HrUserSummary(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    can_approve_leave: bool = False


class EmployeeProfileUpsert(BaseModel):
    employee_number: str | None = Field(default=None, max_length=100)
    company_code: str | None = Field(default=None, max_length=50)
    organizational_unit: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=255)
    manager_user_id: int | None = None
    leave_approver_user_id: int | None = None
    employment_start_date: date | None = None
    employment_end_date: date | None = None
    active: bool = True


class EmployeeProfileRead(BaseModel):
    id: int
    user_id: int
    employee_number: str | None = None
    company_code: str | None = None
    organizational_unit: str | None = None
    job_title: str | None = None
    manager_user_id: int | None = None
    leave_approver_user_id: int | None = None
    employment_start_date: date | None = None
    employment_end_date: date | None = None
    active: bool
    user: HrUserSummary
    manager: HrUserSummary | None = None
    leave_approver: HrUserSummary | None = None
    model_config = ConfigDict(from_attributes=True)


class LeaveEntitlementUpsert(BaseModel):
    year: int = Field(ge=2000, le=2100)
    base_days: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    carried_days: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    adjustment_days: Decimal = Field(default=Decimal("0"), ge=-366, le=366)
    child_days: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    sick_leave_days: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    note: str | None = Field(default=None, max_length=2000)


class LeaveEntitlementRead(LeaveEntitlementUpsert):
    id: int
    employee_id: int
    total_days: Decimal
    model_config = ConfigDict(from_attributes=True)


class LeaveRequestCreate(BaseModel):
    start_date: date
    end_date: date
    employee_comment: str | None = Field(default=None, max_length=2000)


class LeaveDecision(BaseModel):
    version: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=2000)


class LeaveCancel(BaseModel):
    version: int = Field(ge=1)


class LeaveCancellationCreate(BaseModel):
    version: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=2000)


class LeaveRequestRead(BaseModel):
    id: int
    employee_id: int
    employee_user_id: int
    employee_name: str
    approver_user_id: int | None = None
    approver_name: str | None = None
    start_date: date
    end_date: date
    requested_days: Decimal
    status: LeaveRequestStatus
    leave_type: LeaveType = "annual_leave"
    source: str = "workflow"
    source_record_date: date | None = None
    employee_comment: str | None = None
    approver_comment: str | None = None
    submitted_at: datetime
    decided_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_status: LeaveCancellationStatus | None = None
    cancellation_approver_user_id: int | None = None
    cancellation_approver_name: str | None = None
    cancellation_comment: str | None = None
    cancellation_approver_comment: str | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_decided_at: datetime | None = None
    approval_kind: LeaveApprovalKind | None = None
    version: int


class LeaveBalanceRead(BaseModel):
    year: int
    base_days: Decimal
    carried_days: Decimal
    adjustment_days: Decimal
    child_days: Decimal
    total_days: Decimal
    approved_days: Decimal
    pending_days: Decimal
    remaining_days: Decimal
    available_to_request_days: Decimal
    sick_leave_entitlement_days: Decimal
    sick_leave_used_days: Decimal
    sick_leave_remaining_days: Decimal


class HrMeRead(BaseModel):
    profile: EmployeeProfileRead
    balance: LeaveBalanceRead
    leave_requests: list[LeaveRequestRead] = Field(default_factory=list)


class HrSummaryRow(BaseModel):
    employee_id: int
    user_id: int
    employee_number: str | None = None
    full_name: str
    company_code: str | None = None
    organizational_unit: str | None = None
    job_title: str | None = None
    year: int
    total_days: Decimal
    approved_days: Decimal
    pending_days: Decimal
    remaining_days: Decimal
    sick_leave_used_days: Decimal = Decimal("0")
    sick_leave_remaining_days: Decimal = Decimal("0")


class HrAdminEmployeeRow(BaseModel):
    user: HrUserSummary
    profile: EmployeeProfileRead | None = None
    entitlement: LeaveEntitlementRead | None = None


class HrLeaveImportLink(BaseModel):
    user_id: int
    allow_merge: bool = False


class HrLeaveImportRow(BaseModel):
    id: int
    year: int
    full_name: str
    email_hint: str | None = None
    employee_number: str
    employment_start_date: date | None = None
    job_title: str | None = None
    base_days: Decimal
    child_days: Decimal
    sick_leave_days: Decimal
    source_file: str
    source_record_date: date | None = None
    linked_user_id: int | None = None
    linked_user_name: str | None = None
    status: str
    status_message: str | None = None
    absence_count: int
    annual_used_days: Decimal
    sick_used_days: Decimal


class WorkCalendarDayUpsert(BaseModel):
    calendar_date: date
    is_working_day: bool
    label: str | None = Field(default=None, max_length=255)


class WorkCalendarDayRead(WorkCalendarDayUpsert):
    id: int
    model_config = ConfigDict(from_attributes=True)


# CRM
CrmOpportunityStage = Literal["új", "kapcsolatfelvétel", "igényfelmérés", "ajánlat", "tárgyalás", "nyert", "elvesztett"]
CrmActivityType = Literal["telefon", "e-mail", "meeting", "feladat", "jegyzet"]
CrmContractStatus = Literal["tervezet", "aktív", "lejárt", "felmondott", "lezárt"]
CrmCompanyCode = Literal["DRH", "SP", "GXR"]


class ProcurementUserSummary(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)


class ProcurementAttachmentRead(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_by_user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProcurementRequestCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    purpose: str = Field(min_length=1, max_length=5000)
    description: str = Field(min_length=1, max_length=20000)
    total_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="HUF", min_length=3, max_length=3)

    @field_validator("subject", "purpose", "description")
    @classmethod
    def strip_required_text(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("A mező nem lehet üres")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("A pénznem hárombetűs kód legyen")
        return value


class ProcurementRequestUpdate(BaseModel):
    version: int = Field(ge=1)
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    purpose: str | None = Field(default=None, min_length=1, max_length=5000)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    total_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("subject", "purpose", "description")
    @classmethod
    def strip_optional_text(cls, value: str | None):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("A mező nem lehet üres")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None):
        if value is None:
            return value
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("A pénznem hárombetűs kód legyen")
        return value


class ProcurementDecision(BaseModel):
    version: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=5000)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, value: str | None):
        return value.strip() if value and value.strip() else None


class ProcurementWithdraw(BaseModel):
    version: int = Field(ge=1)


class ProcurementRequestRead(BaseModel):
    id: int
    request_number: str
    requester_user_id: int
    subject: str
    purpose: str
    description: str
    total_amount: Decimal
    currency: str
    status: Literal["pending", "approved", "rejected", "withdrawn"]
    approved_by_user_id: int | None = None
    approver_comment: str | None = None
    submitted_at: datetime
    decided_at: datetime | None = None
    withdrawn_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    requester: ProcurementUserSummary
    approver: ProcurementUserSummary | None = None
    attachments: list[ProcurementAttachmentRead] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class ProcurementRequestPage(BaseModel):
    items: list[ProcurementRequestRead] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
    pages: int


class CrmContractServiceLineInput(BaseModel):
    rental_fee: str | None = Field(default=None, max_length=4000)
    operating_fee: str | None = Field(default=None, max_length=4000)
    click_fee: str | None = Field(default=None, max_length=4000)
    included_quantity: str | None = Field(default=None, max_length=4000)
    operator_company: str | None = Field(default=None, max_length=255)
    operator_site: str | None = Field(default=None, max_length=500)
    maintenance_cycle: str | None = Field(default=None, max_length=120)
    device_group: str | None = Field(default=None, max_length=255)
    device_name: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    parts_terms: str | None = Field(default=None, max_length=4000)
    toner_terms: str | None = Field(default=None, max_length=4000)
    travel_labor_terms: str | None = Field(default=None, max_length=4000)
    repair_terms: str | None = Field(default=None, max_length=4000)
    sla: str | None = Field(default=None, max_length=4000)
    replacement_device: str | None = Field(default=None, max_length=4000)


class CrmContractServiceLineRead(CrmContractServiceLineInput):
    id: int
    sort_order: int
    model_config = ConfigDict(from_attributes=True)


class CrmContractCreate(BaseModel):
    customer_id: int
    contract_number: str = Field(min_length=1, max_length=120)
    contract_type: str = Field(min_length=1, max_length=120)
    company_code: CrmCompanyCode = "DRH"
    contracting_party_name: str | None = Field(default=None, max_length=255)
    contracting_party_address: str | None = Field(default=None, max_length=500)
    subject: str | None = Field(default=None, max_length=8000)
    start_date: date | None = None
    end_date: date | None = None
    term_text: str | None = Field(default=None, max_length=255)
    status: CrmContractStatus = "aktív"
    billing_frequency: str | None = Field(default=None, max_length=255)
    payment_terms: str | None = Field(default=None, max_length=255)
    billing_name: str | None = Field(default=None, max_length=255)
    service_confirmation: str | None = Field(default=None, max_length=255)
    e_invoice_email: str | None = Field(default=None, max_length=255)
    price_adjustment_terms: str | None = Field(default=None, max_length=8000)
    sla: str | None = Field(default=None, max_length=8000)
    billing_model: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=8000)
    location_ids: list[int] = Field(default_factory=list)
    asset_ids: list[int] = Field(default_factory=list)
    service_lines: list[CrmContractServiceLineInput] = Field(default_factory=list, max_length=100)


class CrmContractUpdate(BaseModel):
    version: int = Field(ge=1)
    customer_id: int | None = None
    contract_number: str | None = Field(default=None, min_length=1, max_length=120)
    contract_type: str | None = Field(default=None, min_length=1, max_length=120)
    company_code: CrmCompanyCode | None = None
    contracting_party_name: str | None = Field(default=None, max_length=255)
    contracting_party_address: str | None = Field(default=None, max_length=500)
    subject: str | None = Field(default=None, max_length=8000)
    start_date: date | None = None
    end_date: date | None = None
    term_text: str | None = Field(default=None, max_length=255)
    status: CrmContractStatus | None = None
    billing_frequency: str | None = Field(default=None, max_length=255)
    payment_terms: str | None = Field(default=None, max_length=255)
    billing_name: str | None = Field(default=None, max_length=255)
    service_confirmation: str | None = Field(default=None, max_length=255)
    e_invoice_email: str | None = Field(default=None, max_length=255)
    price_adjustment_terms: str | None = Field(default=None, max_length=8000)
    sla: str | None = Field(default=None, max_length=8000)
    billing_model: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=8000)
    location_ids: list[int] | None = None
    asset_ids: list[int] | None = None
    service_lines: list[CrmContractServiceLineInput] | None = Field(default=None, max_length=100)


class CrmContractRead(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    contract_number: str
    contract_type: str
    company_code: CrmCompanyCode
    contracting_party_name: str | None = None
    contracting_party_address: str | None = None
    subject: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    term_text: str | None = None
    status: CrmContractStatus
    billing_frequency: str | None = None
    payment_terms: str | None = None
    billing_name: str | None = None
    service_confirmation: str | None = None
    e_invoice_email: str | None = None
    price_adjustment_terms: str | None = None
    sla: str | None = None
    billing_model: str | None = None
    note: str | None = None
    location_ids: list[int] = Field(default_factory=list)
    asset_ids: list[int] = Field(default_factory=list)
    service_lines: list[CrmContractServiceLineRead] = Field(default_factory=list)
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CrmContractArchiveRead(BaseModel):
    id: int
    archive_number: str
    contract_id: int
    note: str | None = None
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_by_user_id: int | None = None
    uploaded_by_name: str | None = None
    created_at: datetime


class WorkOrderContractOption(BaseModel):
    id: int
    contract_number: str
    contract_type: str
    status: str
    start_date: date | None = None
    end_date: date | None = None
    location_ids: list[int] = Field(default_factory=list)
    asset_ids: list[int] = Field(default_factory=list)


class CrmUserSummary(BaseModel):
    id: int
    full_name: str
    email: EmailStr


class CrmOpportunityCreate(BaseModel):
    customer_id: int
    contact_id: int | None = None
    owner_user_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    stage: CrmOpportunityStage = "új"
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="HUF", min_length=3, max_length=3)
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    source: str | None = Field(default=None, max_length=255)
    next_step: str | None = Field(default=None, max_length=4000)
    lost_reason: str | None = Field(default=None, max_length=4000)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str):
        return value.strip().upper()


class CrmOpportunityUpdate(BaseModel):
    version: int = Field(ge=1)
    customer_id: int | None = None
    contact_id: int | None = None
    owner_user_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    stage: CrmOpportunityStage | None = None
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    source: str | None = Field(default=None, max_length=255)
    next_step: str | None = Field(default=None, max_length=4000)
    lost_reason: str | None = Field(default=None, max_length=4000)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None):
        return value.strip().upper() if value else value


class CrmOpportunityRead(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    contact_id: int | None = None
    contact_name: str | None = None
    owner_user_id: int | None = None
    owner_name: str | None = None
    title: str
    stage: CrmOpportunityStage
    estimated_value: Decimal | None = None
    currency: str
    probability: int | None = None
    expected_close_date: date | None = None
    source: str | None = None
    next_step: str | None = None
    lost_reason: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CrmActivityCreate(BaseModel):
    customer_id: int
    contact_id: int | None = None
    opportunity_id: int | None = None
    work_order_id: int | None = None
    owner_user_id: int | None = None
    activity_type: CrmActivityType
    subject: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    due_at: datetime | None = None
    completed_at: datetime | None = None


class CrmActivityUpdate(BaseModel):
    version: int = Field(ge=1)
    customer_id: int | None = None
    contact_id: int | None = None
    opportunity_id: int | None = None
    work_order_id: int | None = None
    owner_user_id: int | None = None
    activity_type: CrmActivityType | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    due_at: datetime | None = None
    completed_at: datetime | None = None


class CrmActivityOpportunityCreate(BaseModel):
    version: int = Field(ge=1)


class CrmActivityRead(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    contact_id: int | None = None
    contact_name: str | None = None
    opportunity_id: int | None = None
    opportunity_title: str | None = None
    work_order_id: int | None = None
    work_order_number: str | None = None
    owner_user_id: int | None = None
    owner_name: str | None = None
    activity_type: CrmActivityType
    subject: str
    description: str | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CrmCustomerSummary(BaseModel):
    id: int
    name: str
    company_code: str | None = None
    email: str | None = None
    phone: str | None = None
    contact_count: int = 0
    location_count: int = 0
    asset_count: int = 0
    work_order_count: int = 0
    open_opportunity_count: int = 0
    open_pipeline_value: Decimal = Decimal("0")
    last_activity_at: datetime | None = None


class CrmAssetSummary(BaseModel):
    id: int
    internal_id: str
    type: str | None = None
    model: str | None = None
    serial_number: str | None = None
    status: str
    current_location_id: int | None = None


class CrmWorkOrderSummary(BaseModel):
    id: int
    number: str
    status: str
    work_type: str | None = None
    planned_date: date | None = None
    created_at: datetime


class CrmCustomerDetail(BaseModel):
    customer: CustomerRead
    summary: CrmCustomerSummary
    assets: list[CrmAssetSummary] = Field(default_factory=list)
    work_orders: list[CrmWorkOrderSummary] = Field(default_factory=list)
    opportunities: list[CrmOpportunityRead] = Field(default_factory=list)
    activities: list[CrmActivityRead] = Field(default_factory=list)
    contracts: list[CrmContractRead] = Field(default_factory=list)


class CrmDashboardRead(BaseModel):
    customer_count: int
    open_opportunity_count: int
    open_pipeline_value: Decimal
    overdue_activity_count: int
    active_contract_count: int = 0
    expiring_contract_count: int = 0
    opportunities_by_stage: dict[str, int] = Field(default_factory=dict)
    recent_opportunities: list[CrmOpportunityRead] = Field(default_factory=list)
    recent_activities: list[CrmActivityRead] = Field(default_factory=list)
