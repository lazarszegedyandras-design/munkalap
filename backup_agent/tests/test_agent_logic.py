import io
import urllib.error
from datetime import date
from pathlib import Path

import backup_agent.agent as agent


def test_scheduled_kind_uses_last_calendar_day():
    assert agent.scheduled_kind_for_date(date(2026, 8, 30)) == "incremental"
    assert agent.scheduled_kind_for_date(date(2026, 8, 31)) == "master"
    assert agent.scheduled_kind_for_date(date(2026, 2, 28)) == "master"
    assert agent.scheduled_kind_for_date(date(2028, 2, 28)) == "incremental"
    assert agent.scheduled_kind_for_date(date(2028, 2, 29)) == "master"


def test_init_db_adds_control_fields_and_recovers_interrupted_job(tmp_path, monkeypatch):
    control = tmp_path / "control"
    repo = tmp_path / "repo"
    monkeypatch.setattr(agent, "CONTROL_DIR", control)
    monkeypatch.setattr(agent, "REPOSITORY_ROOT", repo)
    monkeypatch.setattr(agent, "APP_BACKUPS", repo / "app_backups")
    monkeypatch.setattr(agent, "DB_PATH", control / "backup-control.sqlite")

    agent.init_db()
    schedule = agent.schedule_payload()
    assert schedule["last_attempt_date"] is None
    assert schedule["last_covered_date"] is None

    with agent.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert {"app_size_bytes", "db_repo_delta_bytes", "db_repo_set_bytes"} <= columns
        restore_columns = {row["name"] for row in conn.execute("PRAGMA table_info(restore_jobs)").fetchall()}
        assert "rollback_restore_backup_id" in restore_columns
        conn.execute(
            "INSERT INTO jobs(id, requested_kind, trigger, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("MST-test", "master", "manual", "running", agent.now_iso()),
        )
        conn.commit()

    agent.init_db()
    with agent.connect() as conn:
        row = conn.execute("SELECT status, error FROM jobs WHERE id='MST-test'").fetchone()
    assert row["status"] == "failed"
    assert "újraindult" in row["error"]




def test_create_restore_rejects_different_deployment_before_queueing(tmp_path, monkeypatch):
    from fastapi import HTTPException

    _configure_temp_agent(tmp_path, monkeypatch)
    with agent.connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs(id, requested_kind, effective_kind, trigger, status, created_at, finished_at, deployment_fingerprint)
            VALUES (?, 'master', 'master', 'manual', 'success', ?, ?, ?)
            """,
            ("MST-other-deploy", agent.now_iso(), agent.now_iso(), "deploy-old"),
        )
        conn.commit()
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-current", {}))
    payload = agent.RestoreRequest(confirmation="VISSZAALLIT")
    try:
        agent.create_restore_job("MST-other-deploy", payload)
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "más deploymenthez" in str(exc.detail)
    else:
        raise AssertionError("Eltérő deployment restore-ját a queue előtt el kell utasítani")
    with agent.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM restore_jobs").fetchone()[0] == 0

def test_runtime_recovery_artifacts_detects_unfinished_restore_dirs(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".restore-stage-RST-test").mkdir()
    (runtime / ".restore-old-RST-test").mkdir()
    (runtime / "normal").mkdir()
    monkeypatch.setattr(agent, "RUNTIME_ROOT", runtime)
    assert agent.runtime_recovery_artifacts() == [
        ".restore-old-RST-test",
        ".restore-stage-RST-test",
    ]


def test_init_db_upgrades_v018_control_database_without_losing_schedule_or_jobs(tmp_path, monkeypatch):
    import sqlite3

    control = tmp_path / "control"
    repo = tmp_path / "repo"
    control.mkdir()
    db_path = control / "backup-control.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, requested_kind TEXT NOT NULL, effective_kind TEXT, trigger TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, local_date TEXT,
            base_master_id TEXT, pgbackrest_label TEXT, deployment_fingerprint TEXT, backup_dir TEXT, size_bytes INTEGER,
            app_size_bytes INTEGER, db_repo_delta_bytes INTEGER, db_repo_set_bytes INTEGER, requested_by_user_id INTEGER,
            requested_by_name TEXT, requested_by_email TEXT, message TEXT, error TEXT
        );
        INSERT INTO settings(key, value) VALUES ('schedule.enabled', 'true');
        INSERT INTO settings(key, value) VALUES ('schedule.daily_time', '22:15');
        INSERT INTO settings(key, value) VALUES ('schedule.timezone', 'Europe/Budapest');
        INSERT INTO jobs(id, requested_kind, effective_kind, trigger, status, created_at, finished_at)
        VALUES ('MST-v018', 'master', 'master', 'manual', 'success', '2026-08-24T10:00:00Z', '2026-08-24T10:01:00Z');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(agent, "CONTROL_DIR", control)
    monkeypatch.setattr(agent, "REPOSITORY_ROOT", repo)
    monkeypatch.setattr(agent, "APP_BACKUPS", repo / "app_backups")
    monkeypatch.setattr(agent, "DB_PATH", db_path)

    agent.init_db()

    assert agent.schedule_payload()["enabled"] is True
    assert agent.schedule_payload()["daily_time"] == "22:15"
    with agent.connect() as conn:
        assert conn.execute("SELECT status FROM jobs WHERE id='MST-v018'").fetchone()["status"] == "success"
        restore_columns = {row["name"] for row in conn.execute("PRAGMA table_info(restore_jobs)").fetchall()}
    assert {"pre_restore_backup_id", "post_restore_backup_id", "rollback_restore_backup_id"} <= restore_columns
    assert agent.restore_recovery_required() is False

def test_job_ids_are_unique_at_subsecond_resolution(tmp_path, monkeypatch):
    control = tmp_path / "control"
    repo = tmp_path / "repo"
    monkeypatch.setattr(agent, "CONTROL_DIR", control)
    monkeypatch.setattr(agent, "REPOSITORY_ROOT", repo)
    monkeypatch.setattr(agent, "APP_BACKUPS", repo / "app_backups")
    monkeypatch.setattr(agent, "DB_PATH", control / "backup-control.sqlite")
    agent.init_db()

    first = agent.new_job_id("master")
    second = agent.new_job_id("master")
    assert first.startswith("MST-")
    assert first != second


def _configure_temp_agent(tmp_path, monkeypatch):
    control = tmp_path / "control"
    repo = tmp_path / "repo"
    runtime = tmp_path / "runtime"
    project = tmp_path / "project"
    runtime.mkdir(parents=True)
    project.mkdir(parents=True)
    (project / "VERSION").write_text("0.19.1\n", encoding="utf-8")
    monkeypatch.setattr(agent, "CONTROL_DIR", control)
    monkeypatch.setattr(agent, "REPOSITORY_ROOT", repo)
    monkeypatch.setattr(agent, "APP_BACKUPS", repo / "app_backups")
    monkeypatch.setattr(agent, "DB_PATH", control / "backup-control.sqlite")
    monkeypatch.setattr(agent, "RUNTIME_ROOT", runtime)
    monkeypatch.setattr(agent, "PROJECT_ROOT", project)
    agent.init_db()
    return runtime, repo


def _insert_job(job_id, requested_kind, trigger="scheduled"):
    with agent.connect() as conn:
        conn.execute(
            "INSERT INTO jobs(id, requested_kind, trigger, status, created_at) VALUES (?, ?, ?, 'queued', ?)",
            (job_id, requested_kind, trigger, agent.now_iso()),
        )
        conn.commit()


def test_backup_status_returns_only_the_requested_job(tmp_path, monkeypatch):
    _configure_temp_agent(tmp_path, monkeypatch)
    _insert_job("MST-first", "master", "manual")
    _insert_job("INC-second", "incremental", "scheduled")

    result = agent.backup_status("INC-second")

    assert result["id"] == "INC-second"
    assert result["requested_kind"] == "incremental"


def test_incremental_without_master_promotes_and_records_database_size(tmp_path, monkeypatch):
    runtime, repo = _configure_temp_agent(tmp_path, monkeypatch)
    (runtime / "document.txt").write_text("master content", encoding="utf-8")
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-a", {"images": {}}))
    monkeypatch.setattr(agent, "ensure_pgbackrest", lambda: None)
    monkeypatch.setattr(agent, "pgbackrest_info", lambda: [])
    monkeypatch.setattr(agent, "quiesce_application", lambda: {})
    monkeypatch.setattr(agent, "resume_application", lambda states: None)
    monkeypatch.setattr(
        agent,
        "pgbackrest_backup",
        lambda kind: {"label": "20260824-120000F", "info": {"repository": {"delta": 100, "size": 100}}},
    )
    monkeypatch.setattr(agent, "write_system_metadata", lambda target: None)
    monkeypatch.setattr(agent, "save_images", lambda target, deployment: None)

    _insert_job("INC-test-master-promotion", "incremental")
    agent.perform_job("INC-test-master-promotion")

    with agent.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id='MST-test-master-promotion'").fetchone()
    assert row is not None
    assert row["status"] == "success"
    assert row["effective_kind"] == "master"
    assert row["base_master_id"] == "MST-test-master-promotion"
    assert row["db_repo_delta_bytes"] == 100
    assert row["size_bytes"] == row["app_size_bytes"] + 100
    backup_dir = repo / row["backup_dir"]
    assert (backup_dir / "app-runtime-full.tar.gz").is_file()
    assert agent.get_setting("schedule.last_run_date")
    assert agent.get_setting("schedule.last_covered_date")


def test_incremental_after_master_keeps_master_base_and_delta(tmp_path, monkeypatch):
    runtime, repo = _configure_temp_agent(tmp_path, monkeypatch)
    (runtime / "document.txt").write_text("master content", encoding="utf-8")
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-a", {"images": {}}))
    monkeypatch.setattr(agent, "ensure_pgbackrest", lambda: None)
    def fake_pgbackrest_info():
        master = agent.latest_master_job()
        if not master or not master["pgbackrest_label"]:
            return []
        return [{"backup": [{"label": master["pgbackrest_label"]}]}]
    monkeypatch.setattr(agent, "pgbackrest_info", fake_pgbackrest_info)
    monkeypatch.setattr(agent, "quiesce_application", lambda: {})
    monkeypatch.setattr(agent, "resume_application", lambda states: None)
    pg_labels = iter([
        {"label": "20260824-120000F", "info": {"repository": {"delta": 100, "size": 100}}},
        {"label": "20260824-120000F_20260824-130000I", "info": {"repository": {"delta": 25, "size": 125}}},
    ])
    monkeypatch.setattr(agent, "pgbackrest_backup", lambda kind: next(pg_labels))
    monkeypatch.setattr(agent, "write_system_metadata", lambda target: None)
    monkeypatch.setattr(agent, "save_images", lambda target, deployment: None)

    _insert_job("MST-first", "master", "manual")
    agent.perform_job("MST-first")
    (runtime / "document.txt").write_text("changed content", encoding="utf-8")
    (runtime / "new.txt").write_text("new", encoding="utf-8")
    _insert_job("INC-second", "incremental", "scheduled")
    agent.perform_job("INC-second")

    with agent.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id='INC-second'").fetchone()
    assert row["status"] == "success"
    assert row["effective_kind"] == "incremental"
    assert row["base_master_id"] == "MST-first"
    assert row["db_repo_delta_bytes"] == 25
    backup_dir = repo / row["backup_dir"]
    assert (backup_dir / "app-runtime-incremental.tar.gz").is_file()
    delta = __import__("json").loads((backup_dir / "runtime-delta.json").read_text(encoding="utf-8"))
    assert delta["changed"] == ["document.txt", "new.txt"]

    monkeypatch.setattr(
        agent,
        "pgbackrest_info",
        lambda: [{"backup": [{"label": "20260824-120000F"}, {"label": "20260824-120000F_20260824-130000I"}]}],
    )
    verified = []
    monkeypatch.setattr(agent, "pgbackrest_verify_set", lambda label: verified.append(label))
    validation = agent.validate_backup("INC-second")
    assert validation["valid"] is True
    assert validation["chain_points"] == 2
    assert validation["pgbackrest_verified"] is True
    assert verified == ["20260824-120000F_20260824-130000I"]

    master = agent.latest_master_job()
    master_manifest = repo / master["backup_dir"] / "manifest.json"
    master_manifest.write_text(master_manifest.read_text(encoding="utf-8") + "corruption", encoding="utf-8")
    from fastapi import HTTPException
    try:
        agent.validate_backup("INC-second")
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("A sérült MASTER láncnak el kell buknia az ellenőrzésen")


def test_init_db_marks_interrupted_restore_and_requires_recovery(tmp_path, monkeypatch):
    _configure_temp_agent(tmp_path, monkeypatch)
    with agent.connect() as conn:
        conn.execute(
            "INSERT INTO restore_jobs(id, backup_id, status, created_at) VALUES (?, ?, 'running', ?)",
            ("RST-test", "MST-target", agent.now_iso()),
        )
        conn.commit()

    agent.init_db()
    with agent.connect() as conn:
        row = conn.execute("SELECT status, error FROM restore_jobs WHERE id='RST-test'").fetchone()
    assert row["status"] == "interrupted"
    assert "host-szintű" in row["error"]
    assert agent.restore_recovery_required() is True


def test_runtime_restore_stage_reconstructs_incremental_chain(tmp_path, monkeypatch):
    runtime, repo = _configure_temp_agent(tmp_path, monkeypatch)
    (runtime / "keep.txt").write_text("v1", encoding="utf-8")
    (runtime / "delete.txt").write_text("delete-me", encoding="utf-8")
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-a", {"images": {}}))
    monkeypatch.setattr(agent, "ensure_pgbackrest", lambda: None)
    monkeypatch.setattr(agent, "pgbackrest_info", lambda: [])
    monkeypatch.setattr(agent, "quiesce_application", lambda: {})
    monkeypatch.setattr(agent, "resume_application", lambda states: None)
    labels = iter([
        {"label": "full-label", "info": {"repository": {"delta": 1, "size": 1}}},
        {"label": "incr-label", "info": {"repository": {"delta": 1, "size": 2}}},
    ])
    monkeypatch.setattr(agent, "pgbackrest_backup", lambda kind: next(labels))
    monkeypatch.setattr(agent, "write_system_metadata", lambda target: None)
    monkeypatch.setattr(agent, "save_images", lambda target, deployment: None)

    _insert_job("MST-stage", "master", "manual")
    agent.perform_job("MST-stage")
    (runtime / "keep.txt").write_text("v2", encoding="utf-8")
    (runtime / "delete.txt").unlink()
    (runtime / "new.txt").write_text("new", encoding="utf-8")
    monkeypatch.setattr(agent, "pgbackrest_info", lambda: [{"backup": [{"label": "full-label"}]}])
    _insert_job("INC-stage", "incremental", "scheduled")
    agent.perform_job("INC-stage")

    with agent.connect() as conn:
        target = conn.execute("SELECT * FROM jobs WHERE id='INC-stage'").fetchone()
    chain = agent.backup_chain(target)
    stage = agent.build_runtime_restore_stage(chain, "RST-stage-test")
    assert (stage / "keep.txt").read_text(encoding="utf-8") == "v2"
    assert not (stage / "delete.txt").exists()
    assert (stage / "new.txt").read_text(encoding="utf-8") == "new"


def test_pgbackrest_restore_uses_selected_set_and_immediate_recovery(monkeypatch):
    requests = []
    monkeypatch.setattr(agent, "runner_post", lambda path, payload=None, **kwargs: requests.append((path, payload, kwargs)) or {"ok": True})

    agent.restore_database_to_label("20260824-120000F_20260824-130000I", "0/13000050")
    assert requests == [(
        "/database/restore",
        {"label": "20260824-120000F_20260824-130000I", "stop_lsn": "0/13000050"},
        {"timeout": 86400},
    )]


def test_restore_event_http_error_preserves_backend_response_body(monkeypatch):
    error = urllib.error.HTTPError(
        url="http://backend:8000/api/backups/internal/restore-event",
        code=422,
        msg="Unprocessable Entity",
        hdrs=None,
        fp=io.BytesIO(b'{"detail":[{"loc":["body","requested_by_email"],"msg":"invalid email"}]}'),
    )
    monkeypatch.setattr(agent.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    try:
        agent.notify_backend_restore_event(
            {
                "id": "RST-test",
                "backup_id": "MST-test",
                "requested_by_email": "acceptance@example.invalid",
            },
            outcome="success",
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "HTTP 422 Unprocessable Entity" in message
        assert "requested_by_email" in message
        assert "invalid email" in message
    else:
        raise AssertionError("A backend HTTP hibájának választestét meg kell őrizni")


def _insert_restore_target_and_job(tmp_path, monkeypatch):
    _configure_temp_agent(tmp_path, monkeypatch)
    backup_dir = agent.REPOSITORY_ROOT / "app_backups" / "MST-target"
    backup_dir.mkdir(parents=True)
    with agent.connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs(
                id, requested_kind, effective_kind, trigger, status, created_at, finished_at,
                base_master_id, pgbackrest_label, deployment_fingerprint, backup_dir
            ) VALUES (?, 'master', 'master', 'manual', 'success', ?, ?, ?, ?, ?, ?)
            """,
            (
                "MST-target", agent.now_iso(), agent.now_iso(), "MST-target", "target-label",
                "deploy-a", "app_backups/MST-target",
            ),
        )
        conn.execute(
            """
            INSERT INTO restore_jobs(id, backup_id, status, created_at, requested_by_name)
            VALUES ('RST-success', 'MST-target', 'queued', ?, 'Admin')
            """,
            (agent.now_iso(),),
        )
        conn.commit()


def test_restore_success_creates_pre_and_post_master(tmp_path, monkeypatch):
    _insert_restore_target_and_job(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "validate_backup", lambda backup_id: {"backup_id": backup_id, "valid": True})
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-a", {"images": {}}))
    monkeypatch.setattr(agent, "backup_chain", lambda row: [row])
    stage = agent.RUNTIME_ROOT / ".fake-stage"
    stage.mkdir()
    monkeypatch.setattr(agent, "build_runtime_restore_stage", lambda chain, restore_id: stage)
    monkeypatch.setattr(agent, "stop_service", lambda service, timeout_seconds=60: None)
    monkeypatch.setattr(agent, "start_service", lambda service: None)
    monkeypatch.setattr(agent, "wait_for_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "wait_for_backend", lambda *args, **kwargs: {"current": "0025", "head": "0025"})
    monkeypatch.setattr(agent, "install_runtime_stage", lambda stage, restore_id: agent.RUNTIME_ROOT / ".fake-old")
    monkeypatch.setattr(agent, "cleanup_runtime_old", lambda old: None)
    monkeypatch.setattr(agent, "pgbackrest_backup_stop_lsn", lambda label: "0/100")
    monkeypatch.setattr(agent, "restore_database_to_label", lambda label, stop_lsn: None)
    monkeypatch.setattr(agent, "notify_backend_restore_event", lambda row, outcome, checks=None: {"audit_chain": {"valid": True}})

    def fake_backup(job_id, leave_quiesced_on_success=False):
        with agent.connect() as conn:
            row = conn.execute("SELECT trigger FROM jobs WHERE id=?", (job_id,)).fetchone()
            conn.execute(
                "UPDATE jobs SET effective_kind='master', status='success', finished_at=?, pgbackrest_label=?, deployment_fingerprint='deploy-a' WHERE id=?",
                (agent.now_iso(), "pre-label" if row["trigger"] == "pre_restore" else "post-label", job_id),
            )
            conn.commit()
        return {
            "job_id": job_id,
            "application_states": {"backend": True, "frontend": True} if row["trigger"] == "pre_restore" else {},
            "pgbackrest_label": "pre-label" if row["trigger"] == "pre_restore" else "post-label",
            "pgbackrest_stop_lsn": "0/100",
        }

    monkeypatch.setattr(agent, "_perform_backup_job", fake_backup)
    agent.perform_restore("RST-success")

    with agent.connect() as conn:
        restore = conn.execute("SELECT * FROM restore_jobs WHERE id='RST-success'").fetchone()
    assert restore["status"] == "success"
    assert restore["pre_restore_backup_id"].startswith("MST-")
    assert restore["post_restore_backup_id"].startswith("MST-")
    assert agent.restore_recovery_required() is False


def test_restore_failure_after_destructive_step_rolls_back_pre_restore_master(tmp_path, monkeypatch):
    _insert_restore_target_and_job(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "validate_backup", lambda backup_id: {"backup_id": backup_id, "valid": True})
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-a", {"images": {}}))
    monkeypatch.setattr(agent, "pgbackrest_backup_stop_lsn", lambda label: "0/200")
    monkeypatch.setattr(agent, "backup_chain", lambda row: [row])
    stage = agent.RUNTIME_ROOT / ".fake-stage-fail"
    stage.mkdir()
    old = agent.RUNTIME_ROOT / ".fake-old-fail"
    old.mkdir()
    monkeypatch.setattr(agent, "build_runtime_restore_stage", lambda chain, restore_id: stage)
    monkeypatch.setattr(agent, "stop_service", lambda service, timeout_seconds=60: None)
    monkeypatch.setattr(agent, "start_service", lambda service: None)
    monkeypatch.setattr(agent, "wait_for_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "wait_for_backend", lambda *args, **kwargs: {"current": "0025", "head": "0025"})
    monkeypatch.setattr(agent, "install_runtime_stage", lambda stage, restore_id: old)
    rollback_runtime_calls = []
    monkeypatch.setattr(agent, "rollback_runtime_swap", lambda value: rollback_runtime_calls.append(value))
    monkeypatch.setattr(agent, "notify_backend_restore_event", lambda row, outcome, checks=None: {"audit_chain": {"valid": True}})
    monkeypatch.setattr(agent, "_stop_application_and_db", lambda: None)

    def fake_backup(job_id, leave_quiesced_on_success=False):
        with agent.connect() as conn:
            row = conn.execute("SELECT trigger FROM jobs WHERE id=?", (job_id,)).fetchone()
            conn.execute(
                "UPDATE jobs SET effective_kind='master', status='success', finished_at=?, pgbackrest_label='pre-label', deployment_fingerprint='deploy-a' WHERE id=?",
                (agent.now_iso(), job_id),
            )
            conn.commit()
        return {
            "job_id": job_id,
            "application_states": {"backend": True, "frontend": True},
            "pgbackrest_label": "pre-label",
            "pgbackrest_stop_lsn": "0/300",
        }

    monkeypatch.setattr(agent, "_perform_backup_job", fake_backup)
    restore_calls = []

    def fake_restore(label, stop_lsn):
        restore_calls.append((label, stop_lsn))
        if len(restore_calls) == 1:
            raise RuntimeError("target restore failed")

    monkeypatch.setattr(agent, "restore_database_to_label", fake_restore)
    agent.perform_restore("RST-success")

    with agent.connect() as conn:
        restore = conn.execute("SELECT * FROM restore_jobs WHERE id='RST-success'").fetchone()
    assert restore["status"] == "failed"
    assert restore["rollback_status"] == "success"
    assert restore["rollback_restore_backup_id"].startswith("MST-")
    with agent.connect() as conn:
        latest_master = conn.execute(
            "SELECT id FROM jobs WHERE status='success' AND effective_kind='master' ORDER BY finished_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    assert latest_master["id"] == restore["rollback_restore_backup_id"]
    assert restore_calls[0] == ("target-label", "0/200")
    assert restore_calls[1] == ("pre-label", "0/300")
    assert rollback_runtime_calls == [old]
    assert agent.restore_recovery_required() is False


def test_pgbackrest_verify_set_uses_selected_backup(monkeypatch):
    requests = []
    monkeypatch.setattr(agent, "runner_post", lambda path, payload=None, **kwargs: requests.append((path, payload, kwargs)) or {"ok": True})
    agent.pgbackrest_verify_set("20260824-120000F_20260824-130000I")
    assert requests == [(
        "/pgbackrest/verify",
        {"label": "20260824-120000F_20260824-130000I"},
        {"timeout": 86400},
    )]


def test_wait_for_database_requires_primary_not_only_pg_isready(monkeypatch):
    responses = iter([
        {"running": True, "ready": False, "state": "recovery"},
        {"running": True, "ready": True, "state": "primary"},
    ])
    monkeypatch.setattr(agent, "runner_get", lambda path: next(responses))
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)
    agent.wait_for_database(attempts=2, delay_seconds=0)


def test_wait_for_backend_requires_http_health_after_alembic(monkeypatch):
    calls = {"health": 0}
    monkeypatch.setattr(agent, "service_is_running", lambda service: True)
    monkeypatch.setattr(agent, "runner_get", lambda path: {
        "running": True,
        "ready": True,
        "current": "0025_admin_backup_permissions",
        "heads": ["0025_admin_backup_permissions"],
    })

    def fake_health():
        calls["health"] += 1
        return calls["health"] >= 2

    monkeypatch.setattr(agent, "backend_health_ready", fake_health)
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)
    result = agent.wait_for_backend(attempts=2, delay_seconds=0)
    assert result == {"current": "0025_admin_backup_permissions", "head": "0025_admin_backup_permissions"}
    assert calls["health"] == 2


def test_validate_backup_rejects_pgbackrest_verify_failure(tmp_path, monkeypatch):
    runtime, repo = _configure_temp_agent(tmp_path, monkeypatch)
    (runtime / "document.txt").write_text("content", encoding="utf-8")
    monkeypatch.setattr(agent, "deployment_fingerprint", lambda: ("deploy-a", {"images": {}}))
    monkeypatch.setattr(agent, "ensure_pgbackrest", lambda: None)
    monkeypatch.setattr(agent, "pgbackrest_info", lambda: [{"backup": [{"label": "full-label"}]}])
    monkeypatch.setattr(agent, "quiesce_application", lambda: {})
    monkeypatch.setattr(agent, "resume_application", lambda states: None)
    monkeypatch.setattr(
        agent,
        "pgbackrest_backup",
        lambda kind: {"label": "full-label", "info": {"repository": {"delta": 1, "size": 1}}},
    )
    monkeypatch.setattr(agent, "write_system_metadata", lambda target: None)
    monkeypatch.setattr(agent, "save_images", lambda target, deployment: None)

    _insert_job("MST-verify-fail", "master", "manual")
    agent.perform_job("MST-verify-fail")

    def fail_verify(label):
        raise RuntimeError("repository corruption")

    monkeypatch.setattr(agent, "pgbackrest_verify_set", fail_verify)
    from fastapi import HTTPException
    try:
        agent.validate_backup("MST-verify-fail")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "fizikai ellenőrzése sikertelen" in str(exc.detail)
    else:
        raise AssertionError("Sikertelen pgBackRest verify esetén a backup validációnak el kell buknia")


def test_v025_init_db_adds_offsite_result_columns(tmp_path, monkeypatch):
    _configure_temp_agent(tmp_path, monkeypatch)
    with agent.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert {"offsite_status", "offsite_snapshot_id", "offsite_finished_at", "offsite_error"} <= columns


def test_v025_offsite_configuration_requires_s3_credentials(monkeypatch):
    monkeypatch.setattr(agent, "OFFSITE_ENABLED", True)
    monkeypatch.setattr(agent, "RESTIC_REPOSITORY", "s3:https://object.example/bucket/workapp")
    monkeypatch.setattr(agent, "RESTIC_PASSWORD_VALUE", "restic-password")
    monkeypatch.setattr(agent, "AWS_ACCESS_KEY_ID_VALUE", "")
    monkeypatch.setattr(agent, "AWS_SECRET_ACCESS_KEY_VALUE", "")
    errors = agent.offsite_configuration_errors()
    assert any("AWS_ACCESS_KEY_ID" in item for item in errors)
    assert any("AWS_SECRET_ACCESS_KEY" in item for item in errors)


def test_v025_offsite_backup_runs_restic_backup_and_retention(tmp_path, monkeypatch):
    _configure_temp_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "OFFSITE_ENABLED", True)
    monkeypatch.setattr(agent, "RESTIC_REPOSITORY", "s3:https://object.example/bucket/workapp")
    monkeypatch.setattr(agent, "RESTIC_PASSWORD_VALUE", "restic-password")
    monkeypatch.setattr(agent, "AWS_ACCESS_KEY_ID_VALUE", "access")
    monkeypatch.setattr(agent, "AWS_SECRET_ACCESS_KEY_VALUE", "secret")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:2] == ["restic", "backup"]:
            return type("R", (), {
                "returncode": 0,
                "stdout": '{"message_type":"summary","snapshot_id":"abc123"}\n',
                "stderr": "",
            })()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(agent, "run", fake_run)
    result = agent.run_offsite_backup("MST-v025")
    assert result["snapshot_id"] == "abc123"
    assert commands[0][:3] == ["restic", "backup", "/repo"]
    assert commands[1][:2] == ["restic", "forget"]
    assert "--prune" in commands[1]
    assert (agent.REPOSITORY_ROOT / "control_state" / "backup-control.sqlite").is_file()
