import ast
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_database_service_passes_configured_postgres_user_to_pgbackrest():
    compose_source = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    database_service = compose_source.split("\n  backend:", maxsplit=1)[0]

    assert "POSTGRES_USER: ${POSTGRES_USER:-workapp}" in database_service
    assert "PGUSER: ${POSTGRES_USER:-workapp}" in database_service


def test_release_version_defaults_match_version_file():
    expected_version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    compose_source = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_source = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert compose_source.count(f"${{APP_VERSION:-{expected_version}}}") >= 4
    assert f"APP_VERSION={expected_version}" in env_source.splitlines()


def test_nginx_upload_limits_leave_multipart_overhead_to_backend_validation():
    nginx_source = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    backend_config = (PROJECT_ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")

    assert "archive_max_size_mb: int = 25" in backend_config
    assert "client_max_body_size 26m;" in nginx_source
    assert "client_max_body_size 51m;" in nginx_source
    assert "client_max_body_size 501m;" in nginx_source
    assert nginx_source.count("proxy_pass http://backend:8000;") >= 5
    assert "proxy_pass http://backend:8000/api/;" not in nginx_source
    assert "limit_req zone=auth_login" in nginx_source
    assert "limit_req zone=api_general" in nginx_source


def test_customer_mutations_and_dashboard_leave_integration_are_release_guarded():
    customer_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "customers.py").read_text(encoding="utf-8")
    location_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "locations.py").read_text(encoding="utf-8")
    dashboard_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "dashboard.py").read_text(encoding="utf-8")
    customer_page = (PROJECT_ROOT / "frontend" / "src" / "pages" / "Customers.jsx").read_text(encoding="utf-8")
    dashboard_page = (PROJECT_ROOT / "frontend" / "src" / "pages" / "Dashboard.jsx").read_text(encoding="utf-8")

    assert customer_router.count("Depends(RequireAdmin)") == 4
    assert location_router.count("Depends(RequireAdmin)") == 2
    assert "eszköz, munkalap, kapcsolattartó vagy CRM szerződés" in location_router
    assert 'LeaveRequest.status == "approved"' in dashboard_router
    assert "Role.name == ROLE_TECHNICIAN" in dashboard_router
    assert '"leave_events": [' in dashboard_router
    assert "const isAdmin = user?.role?.name === 'Admin'" in customer_page
    assert customer_page.count("canManage={isAdmin}") == 2
    assert dashboard_page.index('className="panel calendar-panel"') < dashboard_page.index('className="panel maintenance-planning-panel"')
    assert "calendar?.leave_events || []" in dashboard_page


def test_inactive_locations_are_preserved_but_blocked_from_new_assignments():
    model_source = (PROJECT_ROOT / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    schema_source = (PROJECT_ROOT / "backend" / "app" / "schemas.py").read_text(encoding="utf-8")
    location_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "locations.py").read_text(encoding="utf-8")
    work_order_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "work_orders.py").read_text(encoding="utf-8")
    asset_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "assets.py").read_text(encoding="utf-8")
    customer_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "customers.py").read_text(encoding="utf-8")
    crm_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "crm.py").read_text(encoding="utf-8")
    backup_restore = (PROJECT_ROOT / "backend" / "app" / "services" / "backup_restore.py").read_text(encoding="utf-8")
    customer_importer = (PROJECT_ROOT / "backend" / "app" / "importers" / "customer_assets.py").read_text(encoding="utf-8")
    global_importer = (PROJECT_ROOT / "backend" / "app" / "importers" / "global_workbook.py").read_text(encoding="utf-8")
    migration = (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0026_location_active_status.py").read_text(encoding="utf-8")

    assert 'is_active: Mapped[bool] = mapped_column(Boolean, default=True' in model_source
    assert "class LocationRead(LocationBase):" in schema_source and "is_active: bool" in schema_source
    assert 'action = "aktiválás" if location.is_active else "inaktiválás"' in location_router
    assert "existing_location_id=order.location_id" in work_order_router
    assert "existing_location_id=asset.current_location_id" in asset_router
    assert "existing_location_id=contact.location_id" in customer_router
    assert "existing_location_ids=set(contract.location_ids)" in crm_router
    assert 'row.setdefault("is_active", True)' in backup_restore
    assert "if not location.is_active:" in customer_importer
    assert "if not location.is_active:" in global_importer
    assert 'revision = "0026_location_active_status"' in migration
    assert 'down_revision = "0025_admin_backup_permissions"' in migration


def test_leave_cancellation_requires_approval_and_preserves_older_backups():
    model_source = (PROJECT_ROOT / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    schema_source = (PROJECT_ROOT / "backend" / "app" / "schemas.py").read_text(encoding="utf-8")
    hr_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "hr.py").read_text(encoding="utf-8")
    notification_source = (PROJECT_ROOT / "backend" / "app" / "services" / "notifications.py").read_text(encoding="utf-8")
    backup_restore = (PROJECT_ROOT / "backend" / "app" / "services" / "backup_restore.py").read_text(encoding="utf-8")
    migration = (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0027_leave_cancellation_approval.py").read_text(encoding="utf-8")

    assert "cancellation_status: Mapped[str | None]" in model_source
    assert "cancellation_approver_user_id: Mapped[int | None]" in model_source
    assert "class LeaveCancellationCreate(BaseModel):" in schema_source
    assert 'row.status != "approved"' in hr_router
    assert 'row.cancellation_status = "pending"' in hr_router
    assert 'row.status = "cancelled"' in hr_router
    assert 'LeaveRequest.status == "approved"' in notification_source
    assert 'notification_type="leave_cancellation_pending"' in notification_source
    assert 'row.setdefault("cancellation_status", None)' in backup_restore
    assert 'revision = "0027_leave_cancel_approval"' in migration
    assert 'down_revision = "0026_location_active_status"' in migration


def test_crm_activity_can_create_exactly_one_linked_opportunity():
    schema_source = (PROJECT_ROOT / "backend" / "app" / "schemas.py").read_text(encoding="utf-8")
    crm_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "crm.py").read_text(encoding="utf-8")
    activity_page = (PROJECT_ROOT / "frontend" / "src" / "pages" / "CrmActivities.jsx").read_text(encoding="utf-8")

    assert "class CrmActivityOpportunityCreate(BaseModel):" in schema_source
    assert '@router.post(\n    "/activities/{activity_id}/opportunity"' in crm_router
    assert ".with_for_update()" in crm_router
    assert "if activity.opportunity_id is not None:" in crm_router
    assert 'activity.opportunity_id = opportunity.id' in crm_router
    assert '"CRM_OPPORTUNITY_CREATED_FROM_ACTIVITY"' in crm_router
    assert '"CRM_ACTIVITY_LINKED_TO_OPPORTUNITY"' in crm_router
    assert "Lehetőség létrehozása" in activity_page
    assert "/opportunity`" in activity_page


def test_acceptance_incremental_command_is_windows_powershell_51_safe():
    source = (PROJECT_ROOT / "acceptance-backup-restore.ps1").read_text(encoding="utf-8")
    match = re.search(r'^\s*\$code = "([^"]+)"$', source, flags=re.MULTILINE)

    assert match is not None
    command = match.group(1)
    assert "agent.insert_backup_job('incremental', 'acceptance')" in command
    assert "\n" not in command
    assert '"incremental"' not in command


def test_acceptance_native_stderr_is_captured_before_exit_code_handling():
    source = (PROJECT_ROOT / "acceptance-backup-restore.ps1").read_text(encoding="utf-8")

    assert '$previousErrorActionPreference = $ErrorActionPreference' in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert '$ErrorActionPreference = $previousErrorActionPreference' in source


def test_acceptance_uses_backend_valid_test_email_address():
    source = (PROJECT_ROOT / "acceptance-backup-restore.ps1").read_text(encoding="utf-8")

    assert "acceptance@example.invalid" not in source
    assert source.count('requested_by_email = "acceptance@example.com"') == 2


def test_acceptance_runtime_probe_does_not_write_literal_backslash_n():
    source = (PROJECT_ROOT / "acceptance-backup-restore.ps1").read_text(encoding="utf-8")

    assert '"printf \'%s\' \'$Value\' > /app/runtime/acceptance-probe.txt"' in source
    assert "printf '%s\\\\n'" not in source


def test_host_backup_and_restore_python_commands_are_powershell_51_safe():
    cases = [
        ("backup-munkalap-app.ps1", "activeBackupCode", "python -c $activeBackupCode"),
        ("restore-munkalap-app.ps1", "agentStateCode", '"python", "-c", $agentStateCode'),
    ]
    for filename, variable, invocation in cases:
        source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        match = re.search(rf'^\s*\${variable} = "([^"]+)"$', source, flags=re.MULTILINE)

        assert match is not None, filename
        command = match.group(1)
        assert '"' not in command
        ast.parse(command)
        assert invocation in source


def test_acceptance_polls_one_backup_job_instead_of_unrolling_the_backup_list():
    source = (PROJECT_ROOT / "acceptance-backup-restore.ps1").read_text(encoding="utf-8")
    wait_backup = source.split("function Wait-BackupJob", 1)[1].split("function Wait-RestoreJob", 1)[0]

    assert 'Invoke-AgentJson -Method GET -Path "/backups/$JobId"' in wait_backup
    assert "/backups?limit=" not in wait_backup
    assert "Where-Object" not in wait_backup


def test_cloud_security_migration_follows_procurement_release():
    migration = (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0029_cloud_security_foundation.py").read_text(encoding="utf-8")

    assert 'revision = "0029_cloud_security"' in migration
    assert 'down_revision = "0028_procurement"' in migration


def test_public_release_does_not_publish_database_or_backend_ports_by_default():
    compose_source = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    db_service = compose_source.split("\n  backend:", maxsplit=1)[0]
    backend_service = compose_source.split("\n  backend:", maxsplit=1)[1].split("\n  backup-agent:", maxsplit=1)[0]

    assert "    ports:" not in db_service
    assert '      - "5432"' in db_service
    assert "    ports:" not in backend_service
    assert '      - "8000"' in backend_service
    assert "--forwarded-allow-ips=*" not in (PROJECT_ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")


def test_security_foundation_runtime_configuration_is_release_guarded():
    config_source = (PROJECT_ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    nginx_source = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    frontend_api = (PROJECT_ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")

    assert "ADMIN_MFA_REQUIRED must be true in production" in config_source
    assert "SESSION_COOKIE_SECURE must be true in production" in config_source
    assert "Strict-Transport-Security" in nginx_source
    assert "Content-Security-Policy" in nginx_source
    assert "localStorage.setItem" not in frontend_api
    assert "credentials: 'include'" in frontend_api or 'credentials: "include"' in frontend_api


def test_v024_cloud_security_container_and_csrf_hardening_guards():
    compose_source = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend_dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (PROJECT_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    main_source = (PROJECT_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    auth_source = (PROJECT_ROOT / "backend" / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    config_source = (PROJECT_ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")

    assert "read_only: true" in compose_source
    assert "no-new-privileges:true" in compose_source
    assert "cap_drop:\n      - ALL" in compose_source
    backend_entrypoint = (PROJECT_ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "gosu" not in backend_entrypoint
    assert "su-exec" not in backend_entrypoint
    assert "setpriv" not in backend_entrypoint
    assert "USER 10001:10001" in backend_dockerfile
    assert "USER nginx" in frontend_dockerfile
    assert "MALWARE_SCAN_ENABLED must be true for public production deployments" in config_source
    assert 'request.headers.get("sec-fetch-site")' in main_source
    assert 'request.headers.get("x-csrf-token"' in main_source
    assert "return Token()" in auth_source
    assert "access_token=token" not in auth_source
    assert "0029_cloud_security" in (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0029_cloud_security_foundation.py").read_text(encoding="utf-8")


def test_v024_security_session_tables_are_not_restored_from_logical_backups():
    source = (PROJECT_ROOT / "backend" / "app" / "services" / "backup_restore.py").read_text(encoding="utf-8")
    assert 'BACKUP_VERSION = 16' in source
    assert '"auth_sessions"' in source.split("EPHEMERAL_TABLES", 1)[1].split("\n", 1)[0]
    assert '"security_rate_limits"' in source.split("EPHEMERAL_TABLES", 1)[1].split("\n", 1)[0]
    assert 'row.setdefault("mfa_enabled", False)' in source
    assert 'row.setdefault("mfa_secret_encrypted", None)' in source


def test_physical_restore_invalidates_restored_web_sessions():
    source = (PROJECT_ROOT / "backend" / "app" / "routers" / "backups.py").read_text(encoding="utf-8")
    assert "db.query(AuthSession).delete" in source
    assert "db.query(SecurityRateLimit).delete" in source
    assert '"auth_sessions_invalidated"' in source


def test_v025_public_edge_is_the_only_default_public_entrypoint():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    dev = (PROJECT_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")

    frontend_block = base.split("\n  frontend:", 1)[1].split("\n  clamav:", 1)[0]
    assert "    ports:" not in frontend_block
    assert '      - "3000"' in frontend_block
    assert '127.0.0.1:${APP_PORT:-3000}:3000' in dev
    assert 'image: caddy:2.11.4-alpine' in prod
    assert '      - "80:80"' in prod
    assert '      - "443:443"' in prod
    assert 'PUBLIC_BASE_URL: https://${APP_DOMAIN}' in prod
    assert 'CORS_ORIGINS: https://${APP_DOMAIN}' in prod


def test_v025_production_secrets_and_network_isolation_are_release_guarded():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

    assert "backup_api_net:" in base
    assert "privileged_net:" in base
    backup_block = base.split("\n  backup-agent:", 1)[1].split("\n  backup-runner:", 1)[0]
    assert "      - backup_api_net" in backup_block
    assert "      - privileged_net" in backup_block
    assert "      - app_net" not in backup_block
    assert "DATABASE_URL_FILE: /run/secrets/database_url" in prod
    assert "SECRET_KEY_FILE: /run/secrets/secret_key" in prod
    assert "MFA_ENCRYPTION_KEY_FILE: /run/secrets/mfa_encryption_key" in prod
    assert "POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password" in prod
    assert "BACKUP_AGENT_TOKEN_FILE: /run/secrets/backup_agent_token" in prod
    assert "BACKUP_RUNNER_TOKEN_FILE: /run/secrets/backup_runner_token" in prod
    assert "TRUSTED_PROXY_CIDRS: ${FRONTEND_INTERNAL_IP:-172.30.250.20}/32" in prod
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env.production" in gitignore
    assert "secrets/" in gitignore
    assert ".env.production" in dockerignore
    assert "secrets/**" in dockerignore


def test_v030_docker_socket_and_privileged_network_are_isolated():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend_block = base.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    agent_block = base.split("\n  backup-agent:", 1)[1].split("\n  backup-runner:", 1)[0]
    runner_block = base.split("\n  backup-runner:", 1)[1].split("\n  frontend:", 1)[0]

    assert base.count("/var/run/docker.sock:/var/run/docker.sock") == 1
    assert "/var/run/docker.sock" not in backend_block
    assert "/var/run/docker.sock" not in agent_block
    assert "/var/run/docker.sock:/var/run/docker.sock" in runner_block
    assert "privileged_net" not in backend_block
    assert "      - privileged_net" in agent_block
    assert "      - privileged_net" in runner_block
    assert "    ports:" not in runner_block
    assert "BACKUP_RUNNER_TOKEN" not in backend_block


def test_v030_runtime_database_and_migration_credentials_are_separated():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    entrypoint = (PROJECT_ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")
    migration_entrypoint = (PROJECT_ROOT / "backend" / "migrate-entrypoint.sh").read_text(encoding="utf-8")

    assert "workapp_app:" in base
    assert "workapp_migrate:" in base
    assert "db-role-provisioner:" in base
    assert "\n  migrate:" in base
    assert "alembic upgrade head" not in entrypoint
    assert "alembic upgrade head" in migration_entrypoint
    assert "DATABASE_URL_FILE: /run/secrets/database_url" in prod
    assert "DATABASE_URL_FILE: /run/secrets/database_migration_url" in prod
    backend_prod = prod.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    assert "database_migration_url" not in backend_prod
    assert "database_admin_url" not in backend_prod


def test_v030_backend_and_migrate_use_fixed_non_root_without_runtime_privilege_drop():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    backend_entrypoint = (PROJECT_ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")
    migrate_entrypoint = (PROJECT_ROOT / "backend" / "migrate-entrypoint.sh").read_text(encoding="utf-8")
    acceptance = (PROJECT_ROOT / "deploy" / "vps" / "security-hardening-acceptance.sh").read_text(encoding="utf-8")
    identity_check = (PROJECT_ROOT / "deploy" / "vps" / "check-backend-migrate-identities.sh").read_text(encoding="utf-8")

    backend_block = base.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    migrate_block = base.split("\n  migrate:", 1)[1].split("\n  push-worker:", 1)[0]
    forbidden_switches = ("gosu", "su-exec", "setpriv")

    assert "USER 10001:10001" in dockerfile
    assert "PYTHONPATH=/app" in dockerfile
    assert (PROJECT_ROOT / "backend" / "scripts" / "__init__.py").exists()
    assert "gosu" not in dockerfile
    for source in (backend_entrypoint, migrate_entrypoint):
        assert all(command not in source for command in forbidden_switches)
        assert 'if [ "$(id -u)" = "0" ]' in source
    for block in (backend_block, migrate_block):
        assert 'user: "10001:10001"' in block
        assert "cap_drop:\n      - ALL" in block
        assert "cap_add:" not in block
        assert "SETUID" not in block and "SETGID" not in block
    assert 'DATABASE_URL_FILE' in migrate_entrypoint
    assert '[ ! -r "$DATABASE_URL_FILE" ]' in migrate_entrypoint
    assert "python -m scripts.wait_for_db" in backend_entrypoint
    assert "python -m scripts.wait_for_db" in migrate_entrypoint
    assert "alembic upgrade head" in migrate_entrypoint
    assert "python -m app.seed" in migrate_entrypoint
    assert "exit 0" in migrate_entrypoint
    assert 'scripts/release_tests.py" --suite all' in acceptance
    assert "--entrypoint python" in identity_check
    assert "--no-deps" in identity_check
    assert "EXPECTED_DB_USER=workapp_migrate" in identity_check
    assert "EXPECTED_DB_USER=workapp_app" in identity_check
    assert "preflight-production.sh" not in acceptance
    assert "run-restore-acceptance.sh" not in acceptance


def test_v030_runtime_role_owner_membership_is_revoked_and_checked():
    provisioner = (PROJECT_ROOT / "backend" / "scripts" / "provision_db_roles.py").read_text(encoding="utf-8")
    acceptance = (PROJECT_ROOT / "backend" / "scripts" / "check_db_privileges.py").read_text(encoding="utf-8")
    assert 'sql.SQL("REVOKE {} FROM {}")' in provisioner
    assert "workapp_app must not be a member of workapp_owner" in acceptance
    assert "workapp_migrate must be a member of workapp_owner" in acceptance


def test_v025_offsite_backup_and_monitoring_assets_exist():
    agent_source = (PROJECT_ROOT / "backup_agent" / "agent.py").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "backup_agent" / "Dockerfile").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

    assert "restic" in dockerfile
    assert "def run_offsite_backup" in agent_source
    assert '"offsite": offsite_status_payload()' in agent_source
    assert "RESTIC_REPOSITORY" in prod
    assert "RESTIC_PASSWORD_FILE: /run/secrets/restic_password" in prod
    assert "image: louislam/uptime-kuma:2.5.4" in prod
    assert '127.0.0.1:${UPTIME_KUMA_PORT:-3001}:3001' in prod
    for relative in [
        "deploy/vps/preflight-production.sh",
        "deploy/vps/deploy-production.sh",
        "deploy/vps/acceptance-production.sh",
        "deploy/vps/run-backup-acceptance.sh",
        "deploy/vps/offsite-check.sh",
        "deploy/vps/offsite-restore-stage.sh",
    ]:
        assert (PROJECT_ROOT / relative).is_file()


def test_v025_proxy_preserves_caddy_client_ip_and_https_scheme():
    nginx = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "map $http_x_forwarded_for $client_ip_for_backend" in nginx
    assert "map $http_x_forwarded_proto $client_proto_for_backend" in nginx
    assert "limit_req_zone $client_ip_for_backend" in nginx
    assert "proxy_set_header X-Forwarded-For $client_ip_for_backend;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $client_proto_for_backend;" in nginx



def test_v026_mobile_signature_release_guards():
    models = (PROJECT_ROOT / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    mobile = (PROJECT_ROOT / "backend" / "app" / "routers" / "mobile.py").read_text(encoding="utf-8")
    security = (PROJECT_ROOT / "backend" / "app" / "security.py").read_text(encoding="utf-8")
    backup = (PROJECT_ROOT / "backend" / "app" / "services" / "backup_restore.py").read_text(encoding="utf-8")
    migration = (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0030_mobile_signatures.py").read_text(encoding="utf-8")

    assert 'class MobileDevice(Base)' in models
    assert 'class MobileSession(Base)' in models
    assert 'class WorkOrderCompletionSnapshot(Base)' in models
    assert 'class WorkOrderSignature(Base)' in models
    assert '"typ": "mobile_access"' in security
    assert 'previous_refresh_token_hash' in models
    assert 'MOBILE_WORK_ORDER_SIGNED' in mobile
    assert 'snapshot.source_work_order_version != order.version' in mobile
    assert 'finalized_work_order_version=order.version' in mobile
    assert 'BACKUP_VERSION = 16' in backup
    assert '"mobile_sessions"' in backup.split("EPHEMERAL_TABLES", 1)[1].split("\n", 1)[0]
    assert 'work_order_signatures/' in backup
    assert 'revision = "0030_mobile_signatures"' in migration
    assert 'down_revision = "0029_cloud_security"' in migration


def test_v026_signed_pdf_runtime_dependencies_are_pinned():
    requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert 'reportlab==4.4.9' in requirements
    assert 'Pillow==12.3.0' in requirements
    assert 'fonts-dejavu-core' in dockerfile
    preflight = (PROJECT_ROOT / 'deploy' / 'vps' / 'preflight-production.sh').read_text(encoding='utf-8')
    assert 'MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES' in preflight
    assert 'MOBILE_REFRESH_TOKEN_EXPIRE_DAYS' in preflight
    assert 'MOBILE_SIGNATURE_MAX_SIZE_KB' in preflight
    assert 'WORK_ORDER_ACCEPTANCE_TEXT' in preflight


def test_v027_mobile_photo_evidence_and_android_source_are_release_guarded():
    models = (PROJECT_ROOT / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    mobile = (PROJECT_ROOT / "backend" / "app" / "routers" / "mobile.py").read_text(encoding="utf-8")
    snapshot = (PROJECT_ROOT / "backend" / "app" / "services" / "work_order_completion.py").read_text(encoding="utf-8")
    storage = (PROJECT_ROOT / "backend" / "app" / "services" / "work_order_photo_storage.py").read_text(encoding="utf-8")
    migration = (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0031_mobile_work_order_photos.py").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "mobile" / "package.json").read_text(encoding="utf-8")
    auth = (PROJECT_ROOT / "mobile" / "src" / "services" / "auth.js").read_text(encoding="utf-8")
    assert 'class WorkOrderPhoto(Base)' in models
    assert 'MOBILE_WORK_ORDER_PHOTO_UPLOADED' in mobile
    assert '"photos": photos' in snapshot
    assert 'ImageOps.exif_transpose' in storage
    assert 'scan_bytes(raw, settings)' in storage
    assert 'revision = "0031_mobile_photos"' in migration
    assert 'down_revision = "0030_mobile_signatures"' in migration
    assert '"@capacitor/android": "8.5.1"' in package
    assert '"@capacitor/camera": "8.2.4"' in package
    assert '"@aparajita/capacitor-secure-storage": "8.0.0"' in package
    assert 'SecureStorage.set(' in auth
    assert 'localStorage.setItem' not in auth


def test_v028_push_notifications_and_android_signing_pipeline_are_release_guarded():
    models = (PROJECT_ROOT / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    push = (PROJECT_ROOT / "backend" / "app" / "services" / "push_notifications.py").read_text(encoding="utf-8")
    worker = (PROJECT_ROOT / "backend" / "app" / "push_worker.py").read_text(encoding="utf-8")
    mobile = (PROJECT_ROOT / "backend" / "app" / "routers" / "mobile.py").read_text(encoding="utf-8")
    migration = (PROJECT_ROOT / "backend" / "migrations" / "versions" / "0032_push_notifications.py").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "mobile" / "package.json").read_text(encoding="utf-8")
    mobile_push = (PROJECT_ROOT / "mobile" / "src" / "services" / "push.js").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    backup = (PROJECT_ROOT / "backend" / "app" / "services" / "backup_restore.py").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    acceptance = (PROJECT_ROOT / "deploy" / "vps" / "acceptance-production.sh").read_text(encoding="utf-8")

    assert 'class PushDeliveryOutbox(Base)' in models
    assert 'def enqueue_push_for_notification' in push
    assert 'https://fcm.googleapis.com/v1/projects/' in push
    assert 'def claim_delivery' in worker and 'def process_delivery' in worker
    assert '@router.put("/devices/push-token"' in mobile
    assert '@router.delete("/devices/push-token"' in mobile
    assert 'revision = "0032_push_notifications"' in migration
    assert 'down_revision = "0031_mobile_photos"' in migration
    assert '"@capacitor/push-notifications": "8.1.2"' in package
    assert 'pushNotificationActionPerformed' in mobile_push
    assert 'push-worker:' in compose
    assert 'firebase_service_account' in prod
    assert '"push_delivery_outbox"' in backup.split("EPHEMERAL_TABLES", 1)[1].split("\n", 1)[0]
    assert 'row["push_token"] = None' in backup
    assert "mobile/android/app/google-services.json" in dockerignore
    assert "mobile/keystore/" in dockerignore
    assert "mobile/android-release.env" in dockerignore
    assert "mobile/android/app/google-services.json" in gitignore
    assert "_load_fcm_credentials" in acceptance
    assert "Push worker and Firebase OAuth credential" in acceptance
    for relative in [
        "mobile/scripts/build-android.sh",
        "mobile/scripts/generate-release-keystore.sh",
        "mobile/scripts/configure-android-build.sh",
        "mobile/scripts/release-signing.gradle",
        "mobile/ANDROID_BUILD_SIGNING.md",
    ]:
        assert (PROJECT_ROOT / relative).is_file()


def test_v029_end_to_end_android_release_gates_and_push_smoke_assets_exist():
    users_router = (PROJECT_ROOT / "backend" / "app" / "routers" / "users.py").read_text(encoding="utf-8")
    push_service = (PROJECT_ROOT / "backend" / "app" / "services" / "push_notifications.py").read_text(encoding="utf-8")
    push_smoke = (PROJECT_ROOT / "backend" / "app" / "push_smoke_test.py").read_text(encoding="utf-8")
    users_page = (PROJECT_ROOT / "frontend" / "src" / "pages" / "Users.jsx").read_text(encoding="utf-8")
    mobile_package = (PROJECT_ROOT / "mobile" / "package.json").read_text(encoding="utf-8")
    preflight = (PROJECT_ROOT / "mobile" / "scripts" / "preflight-release.sh").read_text(encoding="utf-8")
    verify = (PROJECT_ROOT / "mobile" / "scripts" / "verify-release-artifacts.sh").read_text(encoding="utf-8")
    install_smoke = (PROJECT_ROOT / "mobile" / "scripts" / "install-smoke-test.sh").read_text(encoding="utf-8")
    vps_smoke = (PROJECT_ROOT / "deploy" / "vps" / "push-smoke-test.sh").read_text(encoding="utf-8")

    assert '@router.post("/{user_id}/mobile-devices/{device_id}/test-push"' in users_router
    assert '"push_token"' not in users_router.split('@router.get("/{user_id}/mobile-devices")', 1)[1].split('@router.delete("/{user_id}/mobile-devices/{device_id}"', 1)[0]
    assert 'def enqueue_test_push_for_device' in push_service
    assert 'notification_type": "system_test"' in push_service
    assert 'python -m app.push_smoke_test' in vps_smoke
    assert 'FCM provider elfogadta' in push_smoke
    assert 'Teszt push' in users_page and 'Mobil eszközök' in users_page
    assert 'android:preflight' in mobile_package
    assert 'android:verify' in mobile_package
    assert 'android:smoke' in mobile_package
    assert 'google-services.json package_name' in preflight
    assert 'MUNKALAP_EXPECTED_SIGNING_CERT_SHA256' in preflight
    assert '$APKSIGNER verify --verbose --print-certs' in verify
    assert 'jarsigner -verify -strict' in verify
    assert '$ADB install -r' in install_smoke


def test_v029_version_tool_keeps_mobile_and_production_release_versions_in_sync():
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    setter = (PROJECT_ROOT / "scripts" / "set_version.py").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / ".env.production.example").read_text(encoding="utf-8")
    mobile = (PROJECT_ROOT / "mobile" / "package.json").read_text(encoding="utf-8")
    mobile_env = (PROJECT_ROOT / "mobile" / ".env.example").read_text(encoding="utf-8")
    preflight = (PROJECT_ROOT / "deploy" / "vps" / "preflight-production.sh").read_text(encoding="utf-8")

    assert f"APP_VERSION={version}" in prod
    assert f'"version": "{version}"' in mobile
    assert f"VITE_APP_VERSION={version}" in mobile_env
    assert f'APP_VERSION:-}}" = "{version}"' in preflight
    assert 'mobile/package.json' in setter
    assert '.env.production.example' in setter
    assert 'docker-compose.production.yml' in setter

def test_v030_hotfix4_uses_canonical_compose_and_explicit_nonroot_entrypoints():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    canonical = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    override = (PROJECT_ROOT / "compose.override.yaml").read_text(encoding="utf-8")
    launcher = (PROJECT_ROOT / "start-v0.30.0-hotfix.ps1").read_text(encoding="utf-8-sig")
    migrate_entrypoint = (PROJECT_ROOT / "backend" / "migrate-entrypoint.sh").read_text(encoding="utf-8")

    assert canonical == base
    assert "services: {}" in override
    backend_block = base.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    provisioner_block = base.split("\n  db-role-provisioner:", 1)[1].split("\n  migrate:", 1)[0]
    migrate_block = base.split("\n  migrate:", 1)[1].split("\n  push-worker:", 1)[0]
    push_block = base.split("\n  push-worker:", 1)[1].split("\n  backup-agent:", 1)[0]

    assert 'entrypoint: ["/bin/sh", "/app/entrypoint.sh"]' in backend_block
    assert 'entrypoint: ["python", "/app/scripts/provision_db_roles.py"]' in provisioner_block
    assert 'entrypoint: ["/bin/sh", "/app/migrate-entrypoint.sh"]' in migrate_block
    assert 'entrypoint: ["python", "-m", "app.push_worker"]' in push_block
    for block in (backend_block, provisioner_block, migrate_block, push_block):
        assert "command: []" in block
        assert "gosu" not in block
        assert "su-exec" not in block
        assert "setpriv" not in block

    assert "migrate-entrypoint v0.30.0-hotfix4" in migrate_entrypoint
    assert '-f $ComposeFile' in launcher
    assert 'down --remove-orphans' in launcher
    assert 'down -v' not in launcher
    assert "COMPOSE_FILE" in launcher



def test_v030_runtime_volume_permissions_are_repaired_without_running_backend_as_root():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "backend" / "runtime-permissions.sh").read_text(encoding="utf-8")
    backend_entrypoint = (PROJECT_ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")

    runtime_block = compose.split("\n  runtime-permissions:", 1)[1].split("\n  backend:", 1)[0]
    backend_block = compose.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    backup_agent_block = compose.split("\n  backup-agent:", 1)[1].split("\n  backup-runner:", 1)[0]

    assert 'user: "0:0"' in runtime_block
    assert 'network_mode: "none"' in runtime_block
    assert "- app_runtime:/app/runtime" in runtime_block
    assert "- CHOWN" in runtime_block
    assert "- FOWNER" in runtime_block
    assert "- DAC_OVERRIDE" in runtime_block
    assert "- ALL" in runtime_block
    assert "no-new-privileges:true" in runtime_block
    assert 'user: "10001:10001"' in backend_block
    assert "runtime-permissions:" in backend_block
    assert "condition: service_completed_successfully" in backend_block
    assert "runtime-permissions:" in backup_agent_block
    assert 'chown -R "$APP_UID:$APP_GID" "$TARGET"' in script
    assert 'chmod -R u+rwX "$TARGET"' in script
    assert "Backend refuses to run as root" in backend_entrypoint


def test_v030_physical_restore_normalizes_runtime_ownership_for_nonroot_backend():
    source = (PROJECT_ROOT / "backup_agent" / "agent.py").read_text(encoding="utf-8")

    assert 'RUNTIME_OWNER_UID = int(os.environ.get("BACKUP_RUNTIME_UID", "10001"))' in source
    assert 'RUNTIME_OWNER_GID = int(os.environ.get("BACKUP_RUNTIME_GID", "10001"))' in source
    assert "def normalize_runtime_permissions(" in source
    assert "os.walk(root, followlinks=False)" in source
    assert "os.lchown(path, RUNTIME_OWNER_UID, RUNTIME_OWNER_GID)" in source
    install_block = source.split("def install_runtime_stage", 1)[1].split("def rollback_runtime_swap", 1)[0]
    rollback_block = source.split("def rollback_runtime_swap", 1)[1].split("def cleanup_runtime_old", 1)[0]
    assert "normalize_runtime_permissions(RUNTIME_ROOT)" in install_block
    assert "normalize_runtime_permissions(RUNTIME_ROOT)" in rollback_block


def test_v031_step2_vps_security_gate_is_release_guarded():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prod = (PROJECT_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    nginx = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    caddy = (PROJECT_ROOT / "deploy" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    preflight = (PROJECT_ROOT / "deploy" / "vps" / "preflight-production.sh").read_text(encoding="utf-8")
    scan = (PROJECT_ROOT / "deploy" / "vps" / "security-scan.sh").read_text(encoding="utf-8")
    host = (PROJECT_ROOT / "deploy" / "vps" / "host-security-check.sh").read_text(encoding="utf-8")
    gate = (PROJECT_ROOT / "deploy" / "vps" / "step2-production-security-gate.sh").read_text(encoding="utf-8")
    restore = (PROJECT_ROOT / "deploy" / "vps" / "offsite-restore-stage.sh").read_text(encoding="utf-8")
    acceptance = (PROJECT_ROOT / "deploy" / "vps" / "acceptance-production.sh").read_text(encoding="utf-8")

    backend_block = base.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    migrate_block = base.split("\n  migrate:", 1)[1].split("\n  push-worker:", 1)[0]
    frontend_block = base.split("\n  frontend:", 1)[1].split("\n  clamav:", 1)[0]
    backend_prod = prod.split("\n  backend:", 1)[1].split("\n  db-role-provisioner:", 1)[0]
    migrate_prod = prod.split("\n  migrate:", 1)[1].split("\n  push-worker:", 1)[0]

    assert "BOOTSTRAP_ADMIN_PASSWORD" not in backend_block
    assert "bootstrap_admin_password" not in backend_prod
    assert "BOOTSTRAP_ADMIN_PASSWORD" in migrate_block
    assert "bootstrap_admin_password" in migrate_prod
    assert "cap_drop:\n      - ALL" in frontend_block
    assert "image: louislam/uptime-kuma:2.5.4" in prod

    assert "limit_conn_zone $client_ip_for_backend" in nginx
    assert "limit_req_status 429" in nginx
    for endpoint in ("/api/mobile/auth/login", "/api/mobile/auth/mfa/verify", "/api/mobile/auth/refresh"):
        assert endpoint in nginx
    assert "protocols tls1.2 tls1.3" in caddy
    assert "@blocked_methods method TRACE CONNECT" in caddy
    assert 'X-Frame-Options "DENY"' in caddy
    assert "Content-Security-Policy" in caddy
    assert "X-Forwarded-For {remote_host}" in caddy

    assert "ADMIN_SSH_CIDR" in preflight
    assert "Production .env contains no plaintext sensitive values" in preflight
    assert "backend must not receive environment key" in preflight
    assert 'PROFILE_ARGS="$PROFILE_ARGS --profile monitoring"' in preflight
    assert "ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969" in scan
    assert "docker image save" in scan
    assert "--timeout 20m" in scan
    assert "--download-db-only" in scan
    assert "Locked application image is unavailable locally" in scan
    assert "/var/run/docker.sock" not in scan
    assert "sshd -T" in host
    assert "NTPSynchronized" in host
    assert "UFW default incoming policy must be deny" in host
    assert "RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE" in gate
    assert "PASS_STEP2_VPS_SECURITY_GATE" in gate
    assert "Running runtime images match the current scanned/pulled" in acceptance
    assert "checksums.sha256" in restore
    assert "Restored checksum mismatch" in restore


def test_v031_step2_security_evidence_is_excluded_from_release_source_and_images():
    release_support = (PROJECT_ROOT / "scripts" / "release_support.py").read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert '"security-results"' in release_support
    assert "security-results/" in gitignore
    assert "security-results/" in dockerignore
