from __future__ import annotations

import ipaddress
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Munkalap és eszköznyilvántartó"
    database_url: str = "postgresql+psycopg2://workapp:workapp@db:5432/workapp"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:3000"
    supplier_name: str = ""
    supplier_address: str = ""
    supplier_phone: str = ""
    supplier_email: str = ""
    supplier_contact: str = ""
    runtime_dir: str = "/app/runtime"
    archive_dir: str = ""
    archive_max_size_mb: int = 25
    procurement_max_size_mb: int = 25
    import_max_size_mb: int = 50
    database_pool_size: int = 5
    database_max_overflow: int = 5
    backup_agent_url: str = "http://backup-agent:8090"
    backup_agent_token: str = ""
    backup_agent_timeout_seconds: float = 30.0
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = ""

    # Internet/cloud security foundation. Development defaults remain usable on
    # localhost; production startup validates that the hardened values are set.
    environment: str = "development"
    public_base_url: str = "http://localhost:3000"
    session_cookie_name: str = "workapp_session"
    csrf_cookie_name: str = "workapp_csrf"
    session_cookie_secure: bool = False
    password_min_length: int = 10
    session_idle_timeout_minutes: int = 60
    session_absolute_timeout_minutes: int = 720
    session_touch_interval_seconds: int = 60
    admin_mfa_required: bool = False
    mfa_encryption_key: str = ""
    mfa_challenge_expire_minutes: int = 5
    sensitive_mfa_max_age_seconds: int = 300
    mfa_step_up_rate_limit_attempts: int = 5
    mfa_step_up_rate_limit_window_seconds: int = 300
    mfa_step_up_rate_limit_block_seconds: int = 900
    login_rate_limit_attempts: int = 5
    login_ip_rate_limit_attempts: int = 50
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_block_seconds: int = 900
    trusted_proxy_cidrs: str = "127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    malware_scan_enabled: bool = False
    malware_scan_host: str = "clamav"
    malware_scan_port: int = 3310
    malware_scan_timeout_seconds: float = 15.0
    malware_scan_fail_closed: bool = False
    docs_enabled: bool = True

    # Mobile/API and signed work-order evidence. Mobile access tokens are kept
    # deliberately short; refresh tokens are opaque, server-tracked and rotated.
    mobile_access_token_expire_minutes: int = 15
    mobile_refresh_token_expire_days: int = 30
    mobile_signature_max_size_kb: int = 1024
    mobile_signature_dir: str = ""
    mobile_photo_dir: str = ""
    mobile_photo_max_size_mb: int = 8
    mobile_photo_max_pixels: int = 12_000_000
    mobile_photo_max_dimension: int = 2048
    business_timezone: str = "Europe/Budapest"
    work_order_acceptance_text_version: str = "1"
    work_order_acceptance_text: str = "A munkalapon feltüntetett munkavégzést és adatokat megismertem és a munkavégzés megtörténtét igazolom."

    # Android push notifications. FCM uses the HTTP v1 API with short-lived
    # OAuth2 credentials minted from a service-account file mounted as a secret.
    push_notifications_enabled: bool = False
    fcm_project_id: str = ""
    fcm_service_account_file: str = ""
    push_worker_poll_seconds: int = 5
    push_worker_lock_timeout_seconds: int = 300
    push_retry_max_attempts: int = 5
    push_android_channel_id: str = "work_orders"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_networks(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_cidrs.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


# A DATABASE_URL és a runtime_dir telepítési beállítás. Ezeket a visszaállítás
# szándékosan nem írja felül, nehogy a célkörnyezet adatbázis-kapcsolata megszakadjon.
RESTORABLE_SETTING_KEYS = {
    "app_name",
    "algorithm",
    "access_token_expire_minutes",
    "cors_origins",
    "supplier_name",
    "supplier_address",
    "supplier_phone",
    "supplier_email",
    "supplier_contact",
}


def runtime_settings_path(settings: Settings) -> Path:
    return Path(settings.runtime_dir) / "application_settings.json"


def export_application_settings(settings: Settings) -> dict[str, Any]:
    data = settings.model_dump()
    return {key: data[key] for key in sorted(RESTORABLE_SETTING_KEYS)}


def _load_secret_files_into_environment() -> None:
    mappings = {
        "DATABASE_URL": "DATABASE_URL_FILE",
        "SECRET_KEY": "SECRET_KEY_FILE",
        "MFA_ENCRYPTION_KEY": "MFA_ENCRYPTION_KEY_FILE",
        "BACKUP_AGENT_TOKEN": "BACKUP_AGENT_TOKEN_FILE",
        "BOOTSTRAP_ADMIN_PASSWORD": "BOOTSTRAP_ADMIN_PASSWORD_FILE",
    }
    for target, file_var in mappings.items():
        if os.getenv(target):
            continue
        path = os.getenv(file_var, "").strip()
        if not path:
            continue
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            os.environ[target] = value


@lru_cache
def get_settings() -> Settings:
    _load_secret_files_into_environment()
    settings = Settings()
    path = runtime_settings_path(settings)
    if not path.exists():
        return settings
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    overrides = {key: value for key, value in stored.items() if key in RESTORABLE_SETTING_KEYS}
    return Settings.model_validate({**settings.model_dump(), **overrides})


def production_security_errors(settings: Settings) -> list[str]:
    """Return configuration errors that make public production startup unsafe."""
    errors: list[str] = []
    if not settings.is_production:
        return errors
    weak_secrets = {"", "change-me-in-production", "change-this-secret-before-production"}
    if settings.secret_key.strip() in weak_secrets or len(settings.secret_key.strip()) < 32:
        errors.append("SECRET_KEY must be a unique production secret of at least 32 characters")
    if not settings.backup_agent_token.strip() or settings.backup_agent_token.startswith("change-") or len(settings.backup_agent_token.strip()) < 32:
        errors.append("BACKUP_AGENT_TOKEN must be a unique production secret of at least 32 characters")
    if "workapp:workapp@" in settings.database_url.lower():
        errors.append("DATABASE_URL must not use the default database password in production")
    try:
        database_username = urlsplit(settings.database_url.replace("postgresql+psycopg2://", "postgresql://", 1)).username
    except ValueError:
        database_username = None
    if database_username != "workapp_app":
        errors.append("DATABASE_URL must use the least-privilege workapp_app role in production")
    if not settings.session_cookie_secure:
        errors.append("SESSION_COOKIE_SECURE must be true in production")
    if settings.password_min_length < 12:
        errors.append("PASSWORD_MIN_LENGTH must be at least 12 in production")
    if not settings.admin_mfa_required:
        errors.append("ADMIN_MFA_REQUIRED must be true in production")
    if settings.sensitive_mfa_max_age_seconds < 60 or settings.sensitive_mfa_max_age_seconds > 900:
        errors.append("SENSITIVE_MFA_MAX_AGE_SECONDS must be between 60 and 900 in production")
    if settings.mfa_step_up_rate_limit_attempts < 1 or settings.mfa_step_up_rate_limit_attempts > 20:
        errors.append("MFA_STEP_UP_RATE_LIMIT_ATTEMPTS must be between 1 and 20 in production")
    if settings.mfa_step_up_rate_limit_window_seconds < 30 or settings.mfa_step_up_rate_limit_window_seconds > 3600:
        errors.append("MFA_STEP_UP_RATE_LIMIT_WINDOW_SECONDS must be between 30 and 3600 in production")
    if settings.mfa_step_up_rate_limit_block_seconds < 60 or settings.mfa_step_up_rate_limit_block_seconds > 86400:
        errors.append("MFA_STEP_UP_RATE_LIMIT_BLOCK_SECONDS must be between 60 and 86400 in production")
    if settings.login_rate_limit_attempts < 3 or settings.login_rate_limit_attempts > 10:
        errors.append("LOGIN_RATE_LIMIT_ATTEMPTS must be between 3 and 10 in production")
    if settings.login_ip_rate_limit_attempts < 10 or settings.login_ip_rate_limit_attempts > 200:
        errors.append("LOGIN_IP_RATE_LIMIT_ATTEMPTS must be between 10 and 200 in production")
    if settings.login_rate_limit_window_seconds < 60 or settings.login_rate_limit_window_seconds > 1800:
        errors.append("LOGIN_RATE_LIMIT_WINDOW_SECONDS must be between 60 and 1800 in production")
    if settings.login_rate_limit_block_seconds < 300 or settings.login_rate_limit_block_seconds > 86400:
        errors.append("LOGIN_RATE_LIMIT_BLOCK_SECONDS must be between 300 and 86400 in production")
    if not settings.mfa_encryption_key.strip() or len(settings.mfa_encryption_key.strip()) < 32:
        errors.append("MFA_ENCRYPTION_KEY must be a separate production secret of at least 32 characters")
    if not settings.public_base_url.lower().startswith("https://"):
        errors.append("PUBLIC_BASE_URL must use https:// in production")
    origins = settings.cors_origin_list
    if not origins:
        errors.append("CORS_ORIGINS must explicitly list the production web origin")
    for origin in origins:
        lowered = origin.lower()
        if origin == "*" or not lowered.startswith("https://") or "localhost" in lowered or "127.0.0.1" in lowered:
            errors.append(f"Unsafe production CORS origin: {origin}")
    proxy_cidrs = settings.trusted_proxy_networks
    if not proxy_cidrs:
        errors.append("TRUSTED_PROXY_CIDRS must contain the exact internal reverse-proxy address in production")
    for cidr in proxy_cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            errors.append(f"Invalid TRUSTED_PROXY_CIDRS entry: {cidr}")
            continue
        if network.prefixlen != network.max_prefixlen:
            errors.append(f"TRUSTED_PROXY_CIDRS must use host CIDRs only in production: {cidr}")
    if settings.session_idle_timeout_minutes <= 0 or settings.session_idle_timeout_minutes > 120:
        errors.append("SESSION_IDLE_TIMEOUT_MINUTES must be between 1 and 120 in production")
    if settings.session_absolute_timeout_minutes <= 0 or settings.session_absolute_timeout_minutes > 1440:
        errors.append("SESSION_ABSOLUTE_TIMEOUT_MINUTES must be between 1 and 1440 in production")
    if not settings.malware_scan_enabled:
        errors.append("MALWARE_SCAN_ENABLED must be true for public production deployments")
    elif not settings.malware_scan_fail_closed:
        errors.append("MALWARE_SCAN_FAIL_CLOSED must be true when malware scanning is enabled in production")
    if settings.docs_enabled:
        errors.append("DOCS_ENABLED must be false in production")
    if settings.mobile_access_token_expire_minutes <= 0 or settings.mobile_access_token_expire_minutes > 30:
        errors.append("MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 30 in production")
    if settings.mobile_refresh_token_expire_days <= 0 or settings.mobile_refresh_token_expire_days > 90:
        errors.append("MOBILE_REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 90 in production")
    if settings.mobile_signature_max_size_kb <= 0 or settings.mobile_signature_max_size_kb > 4096:
        errors.append("MOBILE_SIGNATURE_MAX_SIZE_KB must be between 1 and 4096 in production")
    if settings.mobile_photo_max_size_mb <= 0 or settings.mobile_photo_max_size_mb > 25:
        errors.append("MOBILE_PHOTO_MAX_SIZE_MB must be between 1 and 25 in production")
    if settings.mobile_photo_max_pixels < 1_000_000 or settings.mobile_photo_max_pixels > 40_000_000:
        errors.append("MOBILE_PHOTO_MAX_PIXELS must be between 1000000 and 40000000 in production")
    if settings.mobile_photo_max_dimension < 640 or settings.mobile_photo_max_dimension > 4096:
        errors.append("MOBILE_PHOTO_MAX_DIMENSION must be between 640 and 4096 in production")
    try:
        ZoneInfo(settings.business_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append("BUSINESS_TIMEZONE must be a valid IANA timezone in production")
    if not settings.work_order_acceptance_text_version.strip():
        errors.append("WORK_ORDER_ACCEPTANCE_TEXT_VERSION must not be empty in production")
    if len(settings.work_order_acceptance_text.strip()) < 10:
        errors.append("WORK_ORDER_ACCEPTANCE_TEXT must contain the reviewed customer acceptance statement in production")
    if settings.push_notifications_enabled:
        if not settings.fcm_project_id.strip():
            errors.append("FCM_PROJECT_ID is required when push notifications are enabled")
        if not settings.fcm_service_account_file.strip():
            errors.append("FCM_SERVICE_ACCOUNT_FILE is required when push notifications are enabled")
        if settings.push_worker_poll_seconds < 1 or settings.push_worker_poll_seconds > 60:
            errors.append("PUSH_WORKER_POLL_SECONDS must be between 1 and 60")
        if settings.push_retry_max_attempts < 1 or settings.push_retry_max_attempts > 10:
            errors.append("PUSH_RETRY_MAX_ATTEMPTS must be between 1 and 10")
        if not settings.push_android_channel_id.strip():
            errors.append("PUSH_ANDROID_CHANNEL_ID must not be empty when push notifications are enabled")
    return errors
