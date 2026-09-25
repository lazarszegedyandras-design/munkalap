from __future__ import annotations

import ipaddress
import logging
import re
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, production_security_errors
from .services.backup_restore import BACKUP_VERSION
from .services.malware_scan import malware_scanner_ready
from .version import APP_VERSION, semantic_version_parts
from .database import SessionLocal
from .deps import RequireServiceAccess, RequireHrAccess, RequireCrmAccess
from .request_context import correlation_id_var, ip_address_var, request_id_var, session_id_var, user_agent_var
from .security import decode_mobile_token_claims, decode_token_claims
from .routers import audit_logs, auth, assets, backups, crm, customers, dashboard, exports, hr, imports, locations, materials, mobile, notifications, printer_tracking, procurement, reports, settings as settings_router, users, work_order_archives, work_orders

settings = get_settings()
logger = logging.getLogger(__name__)
app = FastAPI(
    title=settings.app_name,
    version=APP_VERSION,
    openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID", "X-Correlation-ID"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)

_CONTEXT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def _safe_context_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if _CONTEXT_ID_RE.fullmatch(value) else None


def _client_ip(request: Request) -> str | None:
    direct = request.client.host if request.client and request.client.host else None
    if not direct:
        return None
    try:
        direct_ip = ipaddress.ip_address(direct)
        trusted = any(direct_ip in ipaddress.ip_network(cidr, strict=False) for cidr in settings.trusted_proxy_networks)
    except ValueError:
        trusted = False
    if trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            try:
                return str(ipaddress.ip_address(candidate))[:64]
            except ValueError:
                pass
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            try:
                return str(ipaddress.ip_address(real_ip.strip()))[:64]
            except ValueError:
                pass
    return direct[:64]


@app.middleware("http")
async def audit_request_context(request: Request, call_next):
    request_id = _safe_context_id(request.headers.get("x-request-id")) or uuid4().hex
    correlation_id = _safe_context_id(request.headers.get("x-correlation-id")) or request_id
    session_id = None
    authorization = request.headers.get("authorization", "")
    presented_token = None
    if authorization.lower().startswith("bearer "):
        presented_token = authorization[7:].strip()
    elif request.cookies.get(settings.session_cookie_name):
        presented_token = request.cookies.get(settings.session_cookie_name)
    if presented_token:
        claims = decode_token_claims(presented_token) or decode_mobile_token_claims(presented_token)
        if claims and claims.get("sid"):
            session_id = str(claims["sid"])[:100]

    tokens = [
        (request_id_var, request_id_var.set(request_id)),
        (correlation_id_var, correlation_id_var.set(correlation_id)),
        (session_id_var, session_id_var.set(session_id)),
        (ip_address_var, ip_address_var.set(_client_ip(request))),
        (user_agent_var, user_agent_var.set((request.headers.get("user-agent") or "")[:512] or None)),
    ]
    try:
        unsafe_method = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
        cookie_authenticated = bool(request.cookies.get(settings.session_cookie_name)) and not authorization.lower().startswith("bearer ")
        csrf_exempt = request.url.path in {
            "/api/auth/login",
            "/api/auth/mfa/setup",
            "/api/auth/mfa/confirm",
            "/api/auth/mfa/verify",
        }

        # Browser-side cross-site writes are rejected even for login/MFA routes.
        # This blocks login-CSRF and other cross-origin state changes while still
        # allowing non-browser API clients that do not send Origin/Fetch-Metadata.
        origin = request.headers.get("origin")
        fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
        cross_site_write = unsafe_method and (
            fetch_site == "cross-site"
            or (origin is not None and origin not in settings.cors_origin_list)
        )
        if cross_site_write:
            response = JSONResponse(status_code=403, content={"detail": "Nem engedélyezett kérésforrás"})
        elif unsafe_method and cookie_authenticated and not csrf_exempt:
            cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
            header_token = request.headers.get("x-csrf-token", "")
            if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
                response = JSONResponse(status_code=403, content={"detail": "Érvénytelen vagy hiányzó CSRF token"})
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(audit_logs.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(backups.router, prefix="/api")

app.include_router(hr.router, prefix="/api", dependencies=[Depends(RequireHrAccess)])
app.include_router(crm.router, prefix="/api", dependencies=[Depends(RequireCrmAccess)])
app.include_router(procurement.router, prefix="/api")
app.include_router(mobile.router, prefix="/api")

# A Szerviz modul végpontjait backend-szinten is védi a moduljogosultság.
# A meglévő szerepkör-ellenőrzések (Admin / Irodai / Technikus) ezen felül
# továbbra is érvényesek az egyes műveletekre.
service_dependencies = [Depends(RequireServiceAccess)]
app.include_router(customers.router, prefix="/api", dependencies=service_dependencies)
app.include_router(locations.router, prefix="/api", dependencies=service_dependencies)
app.include_router(assets.router, prefix="/api", dependencies=service_dependencies)
app.include_router(printer_tracking.router, prefix="/api", dependencies=service_dependencies)
app.include_router(work_orders.router, prefix="/api", dependencies=service_dependencies)
app.include_router(work_order_archives.router, prefix="/api", dependencies=service_dependencies)
app.include_router(materials.router, prefix="/api", dependencies=service_dependencies)
app.include_router(dashboard.router, prefix="/api", dependencies=service_dependencies)
app.include_router(exports.router, prefix="/api", dependencies=service_dependencies)
app.include_router(imports.router, prefix="/api", dependencies=service_dependencies)
app.include_router(settings_router.router, prefix="/api")


@app.on_event("startup")
def validate_public_production_configuration():
    errors = production_security_errors(settings)
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


@app.on_event("startup")
def apply_packaged_hr_leave_imports():
    # A csomagolt 2026-os RLB forrásadat idempotensen stagingbe kerül,
    # és csak egyértelmű, konfliktusmentes felhasználó-párosításnál alkalmazódik.
    from .database import SessionLocal
    from .services.hr_import import auto_apply_rlb_2026_imports

    db = SessionLocal()
    try:
        stats = auto_apply_rlb_2026_imports(db)
        logger.info("HR RLB 2026 import sync: %s", stats)
    except Exception:
        db.rollback()
        logger.exception("A csomagolt HR szabadságadatok automatikus betöltése sikertelen")
    finally:
        db.close()


@app.get("/api/version", tags=["system"])
def version_info():
    return {
        "application": settings.app_name,
        "version": APP_VERSION,
        "semantic_version": semantic_version_parts(),
        "backup_format_version": BACKUP_VERSION,
    }


@app.get("/api/health/live", tags=["system"])
def health_live():
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["system"])
def health_ready():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Readiness database probe failed: %s", exc)
        content = {"status": "not_ready", "reason": "database_unavailable"}
        if not settings.is_production:
            content["detail"] = str(exc)[:300]
        return JSONResponse(status_code=503, content=content)
    finally:
        db.close()
    if settings.malware_scan_enabled and not malware_scanner_ready(settings):
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "malware_scanner_unavailable"})

    runtime = Path(settings.runtime_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    probe = runtime / ".readiness-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Readiness runtime write probe failed: %s", exc)
        content = {"status": "not_ready", "reason": "runtime_not_writable"}
        if not settings.is_production:
            content["detail"] = str(exc)
        return JSONResponse(status_code=503, content=content)
    return {"status": "ready"}


@app.get("/api/health", tags=["system"])
def health():
    # Backward-compatible liveness alias used by existing deployments/tests.
    return {"status": "ok"}
