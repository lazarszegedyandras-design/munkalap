from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


ROLE_ADMIN = "Admin"
ROLE_OFFICE = "Irodai felhasználó"
ROLE_TECHNICIAN = "Technikus / szerelő"

ASSET_STATUSES = ["aktív", "hibás", "javítás alatt", "selejtezett", "raktáron"]
CONTACT_CATEGORIES = ["Szerviz", "Sales", "Egyéb"]
WORK_ORDER_STATUSES = ["új", "ütemezve", "folyamatban", "várakozik", "kész", "lezárva", "törölve / sztornózva"]
PRIORITIES = ["alacsony", "normál", "sürgős"]
WORK_TYPES = ["karbantartás", "javítás", "eseti javítás", "kiszállítás", "üzembe helyezés"]
LEAVE_REQUEST_STATUSES = ["pending", "approved", "rejected", "cancelled"]
LEAVE_CANCELLATION_STATUSES = ["pending", "approved", "rejected"]
PROCUREMENT_REQUEST_STATUSES = ["pending", "approved", "rejected", "withdrawn"]
LEAVE_TYPES = ["annual_leave", "sick_leave"]
CRM_OPPORTUNITY_STAGES = ["új", "kapcsolatfelvétel", "igényfelmérés", "ajánlat", "tárgyalás", "nyert", "elvesztett"]
CRM_ACTIVITY_TYPES = ["telefon", "e-mail", "meeting", "feladat", "jegyzet"]
CRM_CONTRACT_STATUSES = ["tervezet", "aktív", "lejárt", "felmondott", "lezárt"]
WORK_ORDER_PHOTO_CATEGORIES = ["before", "after", "damage", "meter", "other"]


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    module: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_module_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user_links: Mapped[list["UserPermission"]] = relationship(back_populates="permission", cascade="all, delete-orphan")


class UserPermission(Base):
    __tablename__ = "user_permissions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="permission_links")
    permission: Mapped[Permission] = relationship(back_populates="user_links")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_recovery_codes: Mapped[list[str] | None] = mapped_column(JSON)
    mfa_last_counter: Mapped[int | None] = mapped_column(BigInteger)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")
    assigned_work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="technician", foreign_keys="WorkOrder.technician_id")
    secondary_assigned_work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="secondary_technician", foreign_keys="WorkOrder.secondary_technician_id")
    work_order_edit_sessions: Mapped[list["WorkOrderEditSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    work_order_saved_views: Mapped[list["WorkOrderSavedView"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    uploaded_work_order_archives: Mapped[list["WorkOrderArchive"]] = relationship(back_populates="uploaded_by", foreign_keys="WorkOrderArchive.uploaded_by_user_id")
    uploaded_contract_archives: Mapped[list["CrmContractArchive"]] = relationship(back_populates="uploaded_by", foreign_keys="CrmContractArchive.uploaded_by_user_id")
    permission_links: Mapped[list[UserPermission]] = relationship(back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    employee_profile: Mapped["EmployeeProfile | None"] = relationship(
        back_populates="user", foreign_keys="EmployeeProfile.user_id", uselist=False, passive_deletes=True
    )
    owned_crm_opportunities: Mapped[list["CrmOpportunity"]] = relationship(
        back_populates="owner", foreign_keys="CrmOpportunity.owner_user_id"
    )
    crm_activities: Mapped[list["CrmActivity"]] = relationship(
        back_populates="owner", foreign_keys="CrmActivity.owner_user_id"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mobile_devices: Mapped[list["MobileDevice"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mobile_sessions: Mapped[list["MobileSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def permissions(self) -> list[str]:
        return sorted(link.permission.code for link in self.permission_links if link.permission is not None)

    @property
    def modules(self) -> list[str]:
        from .access_control import module_codes_for_permissions
        return module_codes_for_permissions(self.permissions, is_admin=self.role.name == ROLE_ADMIN)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_auth_sessions_absolute_expires", "absolute_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    user: Mapped["User"] = relationship(back_populates="auth_sessions")


class MobileDevice(Base):
    __tablename__ = "mobile_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "device_uuid", name="uq_mobile_devices_user_uuid"),
        Index("ix_mobile_devices_user_revoked", "user_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_uuid: Mapped[str] = mapped_column(String(128), nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), default="android", nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(64))
    push_token: Mapped[str | None] = mapped_column(String(512))
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    push_token_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="mobile_devices")
    sessions: Mapped[list["MobileSession"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class MobileSession(Base):
    __tablename__ = "mobile_sessions"
    __table_args__ = (
        Index("ix_mobile_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_mobile_sessions_device_revoked", "device_id", "revoked_at"),
        Index("ix_mobile_sessions_absolute_expires", "absolute_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(String(64))
    refresh_generation: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    user: Mapped["User"] = relationship(back_populates="mobile_sessions")
    device: Mapped["MobileDevice"] = relationship(back_populates="sessions")


class SecurityRateLimit(Base):
    __tablename__ = "security_rate_limits"

    bucket_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_employee_profiles_user_id"),
        UniqueConstraint("employee_number", name="uq_employee_profiles_employee_number"),
        Index("ix_employee_profiles_active", "active"),
        Index("ix_employee_profiles_leave_approver", "leave_approver_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    employee_number: Mapped[str | None] = mapped_column(String(100))
    company_code: Mapped[str | None] = mapped_column(String(50), index=True)
    organizational_unit: Mapped[str | None] = mapped_column(String(255), index=True)
    job_title: Mapped[str | None] = mapped_column(String(255))
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    leave_approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    employment_start_date: Mapped[date | None] = mapped_column(Date)
    employment_end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="employee_profile", foreign_keys=[user_id])
    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_user_id])
    leave_approver: Mapped["User | None"] = relationship(foreign_keys=[leave_approver_user_id])
    entitlements: Mapped[list["LeaveEntitlement"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(back_populates="employee", cascade="all, delete-orphan")


class LeaveEntitlement(Base):
    __tablename__ = "leave_entitlements"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", name="uq_leave_entitlements_employee_year"),
        Index("ix_leave_entitlements_year", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    base_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    carried_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    adjustment_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    child_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    sick_leave_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    employee: Mapped[EmployeeProfile] = relationship(back_populates="entitlements")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_employee_status", "employee_id", "status"),
        Index("ix_leave_requests_approver_status", "approver_user_id", "status"),
        Index("ix_leave_requests_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    leave_type: Mapped[str] = mapped_column(String(32), default="annual_leave", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), default="workflow", nullable=False, index=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    source_record_date: Mapped[date | None] = mapped_column(Date)
    employee_comment: Mapped[str | None] = mapped_column(Text)
    approver_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancellation_status: Mapped[str | None] = mapped_column(String(32), index=True)
    cancellation_approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    cancellation_comment: Mapped[str | None] = mapped_column(Text)
    cancellation_approver_comment: Mapped[str | None] = mapped_column(Text)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancellation_decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    employee: Mapped[EmployeeProfile] = relationship(back_populates="leave_requests")
    approver: Mapped[User | None] = relationship(foreign_keys=[approver_user_id])
    cancellation_approver: Mapped[User | None] = relationship(foreign_keys=[cancellation_approver_user_id])


class ProcurementRequestSequence(Base):
    __tablename__ = "procurement_request_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ProcurementRequest(Base):
    __tablename__ = "procurement_requests"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="ck_procurement_requests_total_amount_positive"),
        Index("ix_procurement_requests_requester_status", "requester_user_id", "status"),
        Index("ix_procurement_requests_submitted_at", "submitted_at"),
        Index("ix_procurement_requests_status_submitted", "status", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    requester_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="HUF", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    approver_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    requester: Mapped[User] = relationship(foreign_keys=[requester_user_id])
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by_user_id])
    attachments: Mapped[list["ProcurementAttachment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", passive_deletes=True
    )


class ProcurementAttachment(Base):
    __tablename__ = "procurement_attachments"
    __table_args__ = (
        Index("ix_procurement_attachments_request_created", "procurement_request_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    procurement_request_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    request: Mapped[ProcurementRequest] = relationship(back_populates="attachments")
    uploaded_by: Mapped[User] = relationship(foreign_keys=[uploaded_by_user_id])


class HrLeaveImportPerson(Base):
    __tablename__ = "hr_leave_import_people"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_hr_leave_import_people_source_key"),
        Index("ix_hr_leave_import_people_year", "year"),
        Index("ix_hr_leave_import_people_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_hint: Mapped[str | None] = mapped_column(String(255))
    employee_number: Mapped[str] = mapped_column(String(100), nullable=False)
    employment_start_date: Mapped[date | None] = mapped_column(Date)
    job_title: Mapped[str | None] = mapped_column(String(255))
    base_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    child_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    sick_leave_days: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_record_date: Mapped[date | None] = mapped_column(Date)
    linked_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    status_message: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    linked_user: Mapped[User | None] = relationship(foreign_keys=[linked_user_id])
    absences: Mapped[list["HrLeaveImportAbsence"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class HrLeaveImportAbsence(Base):
    __tablename__ = "hr_leave_import_absences"
    __table_args__ = (
        UniqueConstraint("source_reference", name="uq_hr_leave_import_absences_source_reference"),
        Index("ix_hr_leave_import_absences_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_person_id: Mapped[int] = mapped_column(ForeignKey("hr_leave_import_people.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)

    person: Mapped[HrLeaveImportPerson] = relationship(back_populates="absences")


class WorkCalendarDay(Base):
    __tablename__ = "work_calendar_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
    company_code: Mapped[str | None] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    locations: Mapped[list["Location"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    contacts: Mapped[list["CustomerContact"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    assets: Mapped[list["Asset"]] = relationship(back_populates="customer")
    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="customer")
    crm_opportunities: Mapped[list["CrmOpportunity"]] = relationship(back_populates="customer")
    crm_activities: Mapped[list["CrmActivity"]] = relationship(back_populates="customer")
    crm_contracts: Mapped[list["CrmContract"]] = relationship(back_populates="customer")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    gps_lat: Mapped[str | None] = mapped_column(String(64))
    gps_lng: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)

    customer: Mapped[Customer] = relationship(back_populates="locations")
    assets: Mapped[list["Asset"]] = relationship(back_populates="current_location")
    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="location")
    contacts: Mapped[list["CustomerContact"]] = relationship(back_populates="location")
    crm_contract_links: Mapped[list["CrmContractLocation"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class CustomerContact(Base):
    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    category: Mapped[str] = mapped_column(String(32), default="Egyéb", index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="contacts")
    location: Mapped[Location | None] = relationship(back_populates="contacts")
    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="contact")
    crm_opportunities: Mapped[list["CrmOpportunity"]] = relationship(back_populates="contact")
    crm_activities: Mapped[list["CrmActivity"]] = relationship(back_populates="contact")

    @property
    def location_name(self) -> str | None:
        return self.location.name if self.location else None


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_company_status", "company_code", "status"),
        Index("ix_assets_customer_location", "customer_id", "current_location_id"),
        Index("ix_assets_status_next_maintenance", "status", "next_maintenance_date"),
        Index("ix_assets_maintenance_cycle", "maintenance_cycle_months", "last_maintenance_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    internal_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(150), index=True)
    type: Mapped[str | None] = mapped_column(String(150), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), index=True)
    model: Mapped[str | None] = mapped_column(String(150), index=True)
    category: Mapped[str | None] = mapped_column(String(150), index=True)
    status: Mapped[str] = mapped_column(String(64), default="aktív", index=True, nullable=False)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    internal_use: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    warranty_expiry: Mapped[date | None] = mapped_column(Date)
    last_maintenance_date: Mapped[date | None] = mapped_column(Date, index=True)
    maintenance_cycle_months: Mapped[int | None] = mapped_column(Integer, index=True)
    maintenance_cycle_note: Mapped[str | None] = mapped_column(String(255))
    next_maintenance_date: Mapped[date | None] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    company_code: Mapped[str | None] = mapped_column(String(50), index=True)
    import_source: Mapped[str | None] = mapped_column(String(255))
    import_batch: Mapped[str | None] = mapped_column(String(100), index=True)
    import_row: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    current_location: Mapped[Location | None] = relationship(back_populates="assets")
    customer: Mapped[Customer | None] = relationship(back_populates="assets")
    history: Mapped[list["AssetHistory"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    work_order_links: Mapped[list["WorkOrderAsset"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    meter_readings: Mapped[list["AssetMeterReading"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    components: Mapped[list["AssetComponent"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    component_replacements: Mapped[list["AssetComponentReplacement"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    work_order_archive_links: Mapped[list["WorkOrderArchiveAsset"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    crm_contract_links: Mapped[list["CrmContractAsset"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class AssetMeterReading(Base):
    __tablename__ = "asset_meter_readings"
    __table_args__ = (
        UniqueConstraint("asset_id", "recorded_at", name="uq_asset_meter_recorded_at"),
        Index("ix_asset_meter_asset_recorded", "asset_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    black_white_value: Mapped[int | None] = mapped_column(BigInteger)
    color_value: Mapped[int | None] = mapped_column(BigInteger)
    scan_value: Mapped[int | None] = mapped_column(BigInteger)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), index=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="meter_readings")
    work_order: Mapped["WorkOrder | None"] = relationship()
    recorded_by: Mapped["User | None"] = relationship()


class AssetComponent(Base):
    __tablename__ = "asset_components"
    __table_args__ = (Index("ix_asset_components_asset_active", "asset_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    part_number: Mapped[str | None] = mapped_column(String(150), index=True)
    expected_life_pages: Mapped[int | None] = mapped_column(BigInteger)
    last_replacement_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_replacement_meter: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="components")
    replacements: Mapped[list["AssetComponentReplacement"]] = relationship(back_populates="component", cascade="all, delete-orphan")


class AssetComponentReplacement(Base):
    __tablename__ = "asset_component_replacements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_component_id: Mapped[int] = mapped_column(ForeignKey("asset_components.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id", ondelete="SET NULL"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), index=True)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    replaced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    meter_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="component_replacements")
    component: Mapped[AssetComponent] = relationship(back_populates="replacements")
    material: Mapped["Material | None"] = relationship()
    work_order: Mapped["WorkOrder | None"] = relationship()
    technician: Mapped["User | None"] = relationship()


class AssetHistory(Base):
    __tablename__ = "asset_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="history")
    user: Mapped[User | None] = relationship()
    work_order: Mapped[WorkOrder | None] = relationship(back_populates="asset_history_entries")


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("ix_work_orders_status_planned", "status", "planned_date"),
        Index("ix_work_orders_customer_planned", "customer_id", "planned_date"),
        Index("ix_work_orders_technician_planned", "technician_id", "planned_date"),
        Index("ix_work_orders_secondary_technician_planned", "secondary_technician_id", "planned_date"),
        Index("ix_work_orders_work_type_planned", "work_type", "planned_date"),
        Index("ix_work_orders_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("customer_contacts.id", ondelete="SET NULL"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("crm_contracts.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(64), default="új", index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(64), default="normál", index=True, nullable=False)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    secondary_technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    planned_date: Mapped[date | None] = mapped_column(Date, index=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    work_done: Mapped[str | None] = mapped_column(Text)
    final_status: Mapped[str | None] = mapped_column(String(255))
    labor_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    work_type: Mapped[str | None] = mapped_column(String(64), index=True)
    contract_type: Mapped[str | None] = mapped_column(String(120))
    # Régi adatmező, kizárólag visszamenőleges adatbázis-kompatibilitás miatt marad meg.
    travel_fee: Mapped[float | None] = mapped_column(Numeric(10, 2))
    internal_note: Mapped[str | None] = mapped_column(Text)
    customer_note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    __mapper_args__ = {"version_id_col": version}

    customer: Mapped[Customer] = relationship(back_populates="work_orders")
    location: Mapped[Location | None] = relationship(back_populates="work_orders")
    contact: Mapped[CustomerContact | None] = relationship(back_populates="work_orders")
    contract: Mapped["CrmContract | None"] = relationship(back_populates="work_orders")
    technician: Mapped[User | None] = relationship(back_populates="assigned_work_orders", foreign_keys=[technician_id])
    secondary_technician: Mapped[User | None] = relationship(back_populates="secondary_assigned_work_orders", foreign_keys=[secondary_technician_id])
    asset_links: Mapped[list["WorkOrderAsset"]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    material_lines: Mapped[list["WorkOrderMaterial"]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    asset_history_entries: Mapped[list[AssetHistory]] = relationship(back_populates="work_order")
    edit_sessions: Mapped[list["WorkOrderEditSession"]] = relationship(back_populates="work_order", cascade="all, delete-orphan")
    archives: Mapped[list["WorkOrderArchive"]] = relationship(back_populates="work_order")
    crm_activities: Mapped[list["CrmActivity"]] = relationship(back_populates="work_order")
    completion_snapshots: Mapped[list["WorkOrderCompletionSnapshot"]] = relationship(
        back_populates="work_order", order_by="WorkOrderCompletionSnapshot.revision"
    )
    photos: Mapped[list["WorkOrderPhoto"]] = relationship(
        back_populates="work_order", order_by="WorkOrderPhoto.created_at", cascade="all, delete-orphan"
    )


class WorkOrderPhoto(Base):
    __tablename__ = "work_order_photos"
    __table_args__ = (
        Index("ix_work_order_photos_work_order_created", "work_order_id", "created_at"),
        Index("ix_work_order_photos_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    mobile_device_id: Mapped[int | None] = mapped_column(ForeignKey("mobile_devices.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="photos")
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_user_id])
    mobile_device: Mapped["MobileDevice | None"] = relationship()


class WorkOrderCompletionSnapshot(Base):
    __tablename__ = "work_order_completion_snapshots"
    __table_args__ = (
        UniqueConstraint("work_order_id", "revision", name="uq_work_order_completion_revision"),
        Index("ix_work_order_completion_work_order_created", "work_order_id", "created_at"),
        Index("ix_work_order_completion_sha256", "snapshot_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_work_order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="completion_snapshots")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    signature: Mapped["WorkOrderSignature | None"] = relationship(back_populates="snapshot", uselist=False)


class WorkOrderSignature(Base):
    __tablename__ = "work_order_signatures"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_work_order_signatures_snapshot"),
        Index("ix_work_order_signatures_work_order_signed", "work_order_id", "signed_at"),
        Index("ix_work_order_signatures_pdf_sha256", "signed_pdf_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("work_order_completion_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_role: Mapped[str | None] = mapped_column(String(255))
    acceptance_text: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_text_version: Mapped[str] = mapped_column(String(32), nullable=False)
    signature_storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    signature_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signature_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signed_pdf_storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    signed_pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_pdf_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    finalized_work_order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    technician_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    mobile_device_id: Mapped[int | None] = mapped_column(ForeignKey("mobile_devices.id", ondelete="SET NULL"), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    snapshot: Mapped["WorkOrderCompletionSnapshot"] = relationship(back_populates="signature")
    work_order: Mapped["WorkOrder"] = relationship()
    technician: Mapped["User | None"] = relationship(foreign_keys=[technician_user_id])
    mobile_device: Mapped["MobileDevice | None"] = relationship()


class CrmContract(Base):
    __tablename__ = "crm_contracts"
    __table_args__ = (
        UniqueConstraint("contract_number", name="uq_crm_contracts_contract_number"),
        Index("ix_crm_contracts_customer_status", "customer_id", "status"),
        Index("ix_crm_contracts_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    contract_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    contract_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    company_code: Mapped[str] = mapped_column(String(8), default="DRH", server_default="DRH", nullable=False, index=True)
    contracting_party_name: Mapped[str | None] = mapped_column(String(255))
    contracting_party_address: Mapped[str | None] = mapped_column(String(500))
    subject: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    term_text: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="aktív", nullable=False, index=True)
    billing_frequency: Mapped[str | None] = mapped_column(String(255))
    payment_terms: Mapped[str | None] = mapped_column(String(255))
    billing_name: Mapped[str | None] = mapped_column(String(255))
    service_confirmation: Mapped[str | None] = mapped_column(String(255))
    e_invoice_email: Mapped[str | None] = mapped_column(String(255))
    price_adjustment_terms: Mapped[str | None] = mapped_column(Text)
    sla: Mapped[str | None] = mapped_column(Text)
    billing_model: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="crm_contracts")
    location_links: Mapped[list["CrmContractLocation"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    asset_links: Mapped[list["CrmContractAsset"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    service_lines: Mapped[list["CrmContractServiceLine"]] = relationship(back_populates="contract", cascade="all, delete-orphan", order_by="CrmContractServiceLine.sort_order")
    archives: Mapped[list["CrmContractArchive"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="contract")

    @property
    def customer_name(self) -> str:
        return self.customer.name if self.customer else ""

    @property
    def location_ids(self) -> list[int]:
        return sorted(link.location_id for link in self.location_links)

    @property
    def asset_ids(self) -> list[int]:
        return sorted(link.asset_id for link in self.asset_links)


class CrmContractServiceLine(Base):
    __tablename__ = "crm_contract_service_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("crm_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rental_fee: Mapped[str | None] = mapped_column(Text)
    operating_fee: Mapped[str | None] = mapped_column(Text)
    click_fee: Mapped[str | None] = mapped_column(Text)
    included_quantity: Mapped[str | None] = mapped_column(Text)
    operator_company: Mapped[str | None] = mapped_column(String(255))
    operator_site: Mapped[str | None] = mapped_column(String(500))
    maintenance_cycle: Mapped[str | None] = mapped_column(String(120))
    device_group: Mapped[str | None] = mapped_column(String(255))
    device_name: Mapped[str | None] = mapped_column(String(255))
    serial_number: Mapped[str | None] = mapped_column(String(255))
    parts_terms: Mapped[str | None] = mapped_column(Text)
    toner_terms: Mapped[str | None] = mapped_column(Text)
    travel_labor_terms: Mapped[str | None] = mapped_column(Text)
    repair_terms: Mapped[str | None] = mapped_column(Text)
    sla: Mapped[str | None] = mapped_column(Text)
    replacement_device: Mapped[str | None] = mapped_column(Text)

    contract: Mapped[CrmContract] = relationship(back_populates="service_lines")


class CrmContractArchive(Base):
    __tablename__ = "crm_contract_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    contract_id: Mapped[int] = mapped_column(ForeignKey("crm_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    contract: Mapped[CrmContract] = relationship(back_populates="archives")
    uploaded_by: Mapped[User | None] = relationship(back_populates="uploaded_contract_archives", foreign_keys=[uploaded_by_user_id])


class CrmContractLocation(Base):
    __tablename__ = "crm_contract_locations"

    contract_id: Mapped[int] = mapped_column(ForeignKey("crm_contracts.id", ondelete="CASCADE"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), primary_key=True)

    contract: Mapped[CrmContract] = relationship(back_populates="location_links")
    location: Mapped[Location] = relationship(back_populates="crm_contract_links")


class CrmContractAsset(Base):
    __tablename__ = "crm_contract_assets"

    contract_id: Mapped[int] = mapped_column(ForeignKey("crm_contracts.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), primary_key=True)

    contract: Mapped[CrmContract] = relationship(back_populates="asset_links")
    asset: Mapped[Asset] = relationship(back_populates="crm_contract_links")


class CrmOpportunity(Base):
    __tablename__ = "crm_opportunities"
    __table_args__ = (
        Index("ix_crm_opportunities_customer_stage", "customer_id", "stage"),
        Index("ix_crm_opportunities_owner_stage", "owner_user_id", "stage"),
        Index("ix_crm_opportunities_expected_close", "expected_close_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("customer_contacts.id", ondelete="SET NULL"), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), default="új", nullable=False, index=True)
    estimated_value: Mapped[float | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="HUF", nullable=False)
    probability: Mapped[int | None] = mapped_column(Integer)
    expected_close_date: Mapped[date | None] = mapped_column(Date, index=True)
    source: Mapped[str | None] = mapped_column(String(255))
    next_step: Mapped[str | None] = mapped_column(Text)
    lost_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="crm_opportunities")
    contact: Mapped[CustomerContact | None] = relationship(back_populates="crm_opportunities")
    owner: Mapped[User | None] = relationship(back_populates="owned_crm_opportunities", foreign_keys=[owner_user_id])
    activities: Mapped[list["CrmActivity"]] = relationship(back_populates="opportunity")

    @property
    def customer_name(self) -> str:
        return self.customer.name if self.customer else ""

    @property
    def contact_name(self) -> str | None:
        return self.contact.name if self.contact else None

    @property
    def owner_name(self) -> str | None:
        return self.owner.full_name if self.owner else None


class CrmActivity(Base):
    __tablename__ = "crm_activities"
    __table_args__ = (
        Index("ix_crm_activities_customer_created", "customer_id", "created_at"),
        Index("ix_crm_activities_owner_due", "owner_user_id", "due_at"),
        Index("ix_crm_activities_opportunity", "opportunity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("customer_contacts.id", ondelete="SET NULL"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("crm_opportunities.id", ondelete="SET NULL"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="crm_activities")
    contact: Mapped[CustomerContact | None] = relationship(back_populates="crm_activities")
    opportunity: Mapped[CrmOpportunity | None] = relationship(back_populates="activities")
    work_order: Mapped[WorkOrder | None] = relationship(back_populates="crm_activities")
    owner: Mapped[User | None] = relationship(back_populates="crm_activities", foreign_keys=[owner_user_id])

    @property
    def customer_name(self) -> str:
        return self.customer.name if self.customer else ""

    @property
    def contact_name(self) -> str | None:
        return self.contact.name if self.contact else None

    @property
    def opportunity_title(self) -> str | None:
        return self.opportunity.title if self.opportunity else None

    @property
    def work_order_number(self) -> str | None:
        return self.work_order.number if self.work_order else None

    @property
    def owner_name(self) -> str | None:
        return self.owner.full_name if self.owner else None


class WorkOrderSavedView(Base):
    __tablename__ = "work_order_saved_views"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_work_order_saved_view_user_name"),
        Index("ix_work_order_saved_views_user_default", "user_id", "is_default"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="work_order_saved_views")


class WorkOrderEditSession(Base):
    __tablename__ = "work_order_edit_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    work_order: Mapped[WorkOrder] = relationship(back_populates="edit_sessions")
    user: Mapped[User] = relationship(back_populates="work_order_edit_sessions")


class WorkOrderAsset(Base):
    __tablename__ = "work_order_assets"
    __table_args__ = (UniqueConstraint("work_order_id", "asset_id", name="uq_work_order_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False)

    work_order: Mapped[WorkOrder] = relationship(back_populates="asset_links")
    asset: Mapped[Asset] = relationship(back_populates="work_order_links")


class WorkOrderArchive(Base):
    __tablename__ = "work_order_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), index=True)
    source_number: Mapped[str | None] = mapped_column(String(100), index=True)
    work_date: Mapped[date | None] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    work_order: Mapped[WorkOrder | None] = relationship(back_populates="archives")
    asset_links: Mapped[list["WorkOrderArchiveAsset"]] = relationship(back_populates="archive", cascade="all, delete-orphan")
    uploaded_by: Mapped[User | None] = relationship(back_populates="uploaded_work_order_archives", foreign_keys=[uploaded_by_user_id])


class WorkOrderArchiveAsset(Base):
    __tablename__ = "work_order_archive_assets"
    __table_args__ = (UniqueConstraint("archive_id", "asset_id", name="uq_work_order_archive_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int] = mapped_column(ForeignKey("work_order_archives.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True)

    archive: Mapped[WorkOrderArchive] = relationship(back_populates="asset_links")
    asset: Mapped[Asset] = relationship(back_populates="work_order_archive_links")


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="db", nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    stock: Mapped[float | None] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(Text)

    work_order_lines: Mapped[list["WorkOrderMaterial"]] = relationship(back_populates="material")


class WorkOrderMaterial(Base):
    __tablename__ = "work_order_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(Text)

    work_order: Mapped[WorkOrder] = relationship(back_populates="material_lines")
    material: Mapped[Material] = relationship(back_populates="work_order_lines")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str | None] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(String(100), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user: Mapped[User] = relationship(back_populates="notifications")


class PushDeliveryOutbox(Base):
    __tablename__ = "push_delivery_outbox"
    __table_args__ = (
        UniqueConstraint("device_id", "dedupe_key", name="uq_push_delivery_device_dedupe"),
        Index("ix_push_delivery_status_due", "status", "next_attempt_at"),
        Index("ix_push_delivery_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Legacy kapcsolat a felhasználói rekordhoz. Törölt felhasználónál az FK
    # nullázódhat, ezért a hiteles auditazonosságot az alábbi snapshot mezők
    # őrzik meg változatlanul.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_user_id: Mapped[int | None] = mapped_column(Integer)
    actor_name: Mapped[str | None] = mapped_column(String(255))
    actor_email: Mapped[str | None] = mapped_column(String(255))
    actor_role: Mapped[str | None] = mapped_column(String(100))

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_display_id: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=False)

    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    changes: Mapped[dict | None] = mapped_column(JSON)

    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    session_id: Mapped[str | None] = mapped_column(String(100), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    result: Mapped[str] = mapped_column(String(32), default="success", nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", nullable=False, index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user: Mapped[User | None] = relationship()


class AuditChainState(Base):
    __tablename__ = "audit_chain_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
