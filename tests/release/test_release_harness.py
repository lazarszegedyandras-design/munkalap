from __future__ import annotations
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from release_support import (clean_environment, copy_snapshot, image_tags, load_manifest,
    runtime_model, safe_source_path, validate_runtime_model, redact)
import release_tests
from check_release_images import GROUP, OWNED, verify

PROJECT = "munkalap-test-aabbccddeeff"
IMAGES = {name: "sha256:" + (str(i) * 64) for i, name in enumerate(
    ("backend", "db", "frontend", "backup-agent", "backup-runner", "python-tests", "node-tests"), 1)}
CREDENTIALS = {key: "ephemeral-test-only-" + key for key in ("admin", "app", "migrate", "key", "mfa", "bootstrap")}


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.model = runtime_model(PROJECT, IMAGES, CREDENTIALS)

    def test_default_model_is_isolated(self):
        validate_runtime_model(self.model, PROJECT, IMAGES)
        self.assertNotIn("volumes", self.model)
        for service in self.model["services"].values():
            self.assertNotIn("ports", service)
            self.assertNotIn("volumes", service)
            self.assertNotIn("secrets", service)

    def test_production_environment_is_not_inherited(self):
        dirty = {"PATH": "/bin", "DOCKER_CONTEXT": "desktop-linux", "COMPOSE_FILE": "evil.yml",
            "COMPOSE_PROJECT_NAME": "munkalap", "DATABASE_URL": "production", "DB_ADMIN_URL": "production",
            "SECRET_KEY": "secret", "ENV_FILE": ".env.production", "PYTHONPATH": "/evil", "APP_VERSION": "old"}
        cleaned = clean_environment(dirty)
        self.assertEqual(cleaned["DOCKER_CONTEXT"], "desktop-linux")
        for key in set(dirty)-{"PATH", "DOCKER_CONTEXT"}:
            self.assertNotIn(key, cleaned)

    def test_windows_programfiles_is_preserved_for_docker_cli_plugins(self):
        dirty = {
            "PATH": r"C:\Program Files\Docker\Docker\resources\bin",
            "ProgramFiles": r"C:\Program Files",
            "ProgramW6432": r"C:\Program Files",
            "COMPOSE_FILE": "evil.yml",
            "DATABASE_URL": "production",
        }
        cleaned = clean_environment(dirty)
        self.assertEqual(cleaned["ProgramFiles"], r"C:\Program Files")
        self.assertNotIn("ProgramW6432", cleaned)
        self.assertNotIn("COMPOSE_FILE", cleaned)
        self.assertNotIn("DATABASE_URL", cleaned)

    def test_host_runtime_mount_is_rejected(self):
        self.model["services"]["backend"]["volumes"] = ["app_runtime:/app/runtime"]
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_docker_socket_is_rejected(self):
        self.model["services"]["python-tests"]["volumes"] = ["/var/run/docker.sock:/var/run/docker.sock"]
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_published_port_is_rejected(self):
        self.model["services"]["test-db"]["ports"] = ["5432:5432"]
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_production_database_url_is_rejected(self):
        self.model["services"]["backend"]["environment"]["DATABASE_URL"] = "postgresql://app:pw@db:5432/workapp"
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_file_secret_is_rejected(self):
        self.model["services"]["backend"]["environment"]["DATABASE_URL_FILE"] = "/run/secrets/database_url"
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_extra_network_is_rejected(self):
        self.model["services"]["backend"]["networks"].append("data_net")
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_external_test_network_is_rejected(self):
        self.model["networks"]["test_net"]["external"] = True
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_host_network_is_rejected(self):
        self.model["services"]["backend"]["network_mode"] = "host"
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_production_project_name_is_rejected(self):
        with self.assertRaises(ValueError): runtime_model("munkalap", IMAGES, CREDENTIALS)

    def test_mixed_backend_image_id_is_rejected(self):
        self.model["services"]["migrate"]["image"] = IMAGES["frontend"]
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_environment_file_is_rejected(self):
        self.model["services"]["backend"]["env_file"] = [".env.production"]
        with self.assertRaises(ValueError): validate_runtime_model(self.model, PROJECT, IMAGES)

    def test_unit_tests_have_no_network(self):
        self.assertEqual(self.model["services"]["python-tests"]["network_mode"], "none")
        self.assertEqual(self.model["services"]["node-tests"]["network_mode"], "none")

    def test_tests_do_not_inherit_app_entrypoints(self):
        self.assertEqual(self.model["services"]["python-tests"]["entrypoint"], ["python", "-m", "pytest"])
        self.assertEqual(self.model["services"]["legacy-migrate"]["entrypoint"], ["alembic"])
        self.assertEqual(self.model["services"]["migrate"]["entrypoint"], ["/bin/sh", "/app/migrate-entrypoint.sh"])

    def test_credentials_are_redacted(self):
        payload = json.dumps(self.model)
        cleaned = redact(payload, CREDENTIALS.values())
        for value in CREDENTIALS.values(): self.assertNotIn(value, cleaned)


class SnapshotTests(unittest.TestCase):
    def fixture(self, path):
        (path/"VERSION").write_text("0.30.1\n")
        data = {"format": 1, "version": "0.30.1", "files": {"VERSION": hashlib.sha256((path/"VERSION").read_bytes()).hexdigest()}}
        (path/"release-source-manifest.json").write_text(json.dumps(data))
        return data

    def test_snapshot_does_not_copy_unlisted_env_secrets_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"source"; source.mkdir(); self.fixture(source)
            (source/".env").write_text("DATABASE_URL=production")
            (source/"secrets").mkdir(); (source/"secrets"/"secret_key").write_text("private")
            data,_ = load_manifest(source); copy_snapshot(source,root/"snapshot",data)
            self.assertFalse((root/"snapshot"/".env").exists())
            self.assertFalse((root/"snapshot"/"secrets").exists())

    def test_changed_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root); (root/"VERSION").write_text("0.30.2")
            with self.assertRaises(ValueError): load_manifest(root)

    def test_unsafe_manifest_paths_are_refused(self):
        for path in ("../.env", "/etc/passwd", "C:/private", "secrets/key", "backend/.env", "mobile/keystore/key.jks", "security-results/report.json", "Munkalap-backups/backup.tar", "imports/customer.xlsx", "backend/app/data/company_profiles.json", "BACKEND/APP/DATA/COMPANY_PROFILES.JSON", "backend/app/data/customer_assets_20260616.json", "backend/app/data/hr_leave_2026_rlb.json", "backend/migrations/versions/0024_contract_details_archives_hr_calendar.py", "a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError): safe_source_path(path)

    def test_symlink_source_is_refused(self):
        if not hasattr(os, "symlink"): self.skipTest("Symlink unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root)
            (root/"VERSION").rename(root/"other")
            try: (root/"VERSION").symlink_to(root/"other")
            except OSError: self.skipTest("Symlink permission unavailable")
            with self.assertRaises(ValueError): load_manifest(root)


@unittest.skipUnless(os.name == "posix", "POSIX entrypoint execution is exercised in Linux test container")
class EntrypointExecutionTests(unittest.TestCase):
    def invoke(self, script, arguments=(), python_code=0, alembic_code=0, uid=10001):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); trace=directory/"trace"
            # The release test container intentionally has a read-only rootfs and
            # writable tmpfs mounts may be noexec. Use build-time executable stubs
            # there; retain the temporary-stub fallback for direct POSIX host runs.
            baked_tools = Path("/opt/release-entrypoint-test-bin")
            if baked_tools.is_dir():
                tools = baked_tools
            else:
                tools=directory/"bin"; tools.mkdir()
                bodies={"id": '#!/bin/sh\nprintf "%s\\n" "${TEST_UID:-10001}"\n',
                        "python": '#!/bin/sh\necho "python $*" >> "$TRACE"\nexit "${TEST_PYTHON_CODE:-0}"\n',
                        "alembic": '#!/bin/sh\necho "alembic $*" >> "$TRACE"\nexit "${TEST_ALEMBIC_CODE:-0}"\n',
                        "uvicorn": '#!/bin/sh\necho "uvicorn $*" >> "$TRACE"\nexit 0\n'}
                for name, content in bodies.items():
                    (tools/name).write_text(content); (tools/name).chmod(0o755)
            env={
                "PATH":str(tools)+":/usr/bin:/bin",
                "TRACE":str(trace),
                "RUNTIME_DIR":str(directory),
                "TEST_UID":str(uid),
                "TEST_PYTHON_CODE":str(python_code),
                "TEST_ALEMBIC_CODE":str(alembic_code),
            }
            result=subprocess.run(["sh",str(ROOT/"backend"/script),*arguments], env=env, capture_output=True, text=True)
            return result.returncode, trace.read_text() if trace.exists() else "", result.stdout+result.stderr

    def test_backend_rejects_unexpected_test_command_before_any_side_effect(self):
        code,trace,_=self.invoke("entrypoint.sh", ["pytest", "-q"])
        self.assertEqual(code,64); self.assertEqual(trace,"")

    def test_migrate_rejects_heads_command_instead_of_upgrading(self):
        code,trace,_=self.invoke("migrate-entrypoint.sh", ["alembic", "heads"])
        self.assertEqual(code,64); self.assertEqual(trace,"")

    def test_backend_normal_command_still_launches_server(self):
        code,trace,_=self.invoke("entrypoint.sh")
        self.assertEqual(code,0); self.assertIn("python -m scripts.wait_for_db",trace); self.assertIn("uvicorn app.main:app",trace)
        self.assertNotIn("alembic",trace)

    def test_migrate_normal_command_preserves_wait_upgrade_seed_order(self):
        code,trace,_=self.invoke("migrate-entrypoint.sh")
        self.assertEqual(code,0)
        self.assertEqual(trace.splitlines(),["python -m scripts.wait_for_db","alembic upgrade head","python -m app.seed"])

    def test_wait_failure_does_not_run_migrations_or_server(self):
        for script in ("entrypoint.sh","migrate-entrypoint.sh"):
            code,trace,_=self.invoke(script,python_code=27)
            self.assertEqual(code,27);self.assertNotIn("alembic",trace);self.assertNotIn("uvicorn",trace)

    def test_failed_migration_does_not_seed(self):
        code,trace,_=self.invoke("migrate-entrypoint.sh",alembic_code=29)
        self.assertEqual(code,29);self.assertNotIn("app.seed",trace)

    def test_root_is_still_refused(self):
        for script in ("entrypoint.sh","migrate-entrypoint.sh"):
            code,trace,_=self.invoke(script,uid=0)
            self.assertNotEqual(code,0); self.assertEqual(trace,"")


class ImageIdentityTests(unittest.TestCase):
    def model(self):
        return {"name":"munkalap", "services": {s:{"image":"munkalap-"+("backend" if s in GROUP else s)+":0.30.1"} for s in OWNED}}

    def call(self, command):
        if command[0:2]==["image","inspect"]:
            kind = "backend" if "backend:" in command[-1] else command[-1]
            return json.dumps({"Id": "sha256:"+hashlib.sha256(kind.encode()).hexdigest(), "Config":{"Labels":{"hu.lunait.release.version":"0.30.1"}}})
        raise AssertionError(command)

    def test_shared_built_backend_identity_passes(self):
        out=verify(self.model(),"0.30.1",call=self.call)
        self.assertEqual(len({out[s]["image_id"] for s in GROUP}),1)

    def test_service_specific_stale_migrate_image_is_refused(self):
        model=self.model();model["services"]["migrate"]["image"]="munkalap-migrate:0.30.0"
        with self.assertRaises(RuntimeError):verify(model,"0.30.1",call=self.call)

    def test_old_release_label_is_refused(self):
        with self.assertRaises(RuntimeError):
            verify(self.model(),"0.30.1",call=lambda cmd:json.dumps({"Id":"sha256:abc","Config":{"Labels":{"hu.lunait.release.version":"0.30.0"}}}))


class RunnerFailureTests(unittest.TestCase):
    def test_nonzero_exit_is_preserved_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=release_tests.Runner(tmp, {}, ["DO-NOT-LOG-ME"])
            fake=subprocess.CompletedProcess(["fake"],17,"failure DO-NOT-LOG-ME")
            with patch("release_tests.subprocess.run",return_value=fake), self.assertRaises(release_tests.CommandFailed):
                runner.command("failed-test",["fake"])
            self.assertEqual(runner.results[0]["exit_code"],17)
            self.assertNotIn("DO-NOT-LOG-ME",(Path(tmp)/"01-failed-test.log").read_text())

    def test_timeout_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=release_tests.Runner(tmp,{},[])
            with patch("release_tests.subprocess.run",side_effect=subprocess.TimeoutExpired("test",1)), self.assertRaises(release_tests.CommandFailed):
                runner.command("timeout",["fake"])
            self.assertEqual(runner.results[0]["exit_code"],124)

    def test_missing_docker_is_blocked_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"root";root.mkdir();SnapshotTests().fixture(root)
            with patch.object(release_tests,"ROOT",root), patch("release_tests.subprocess.run",side_effect=FileNotFoundError("docker")):
                code=release_tests.main(["--output",str(Path(tmp)/"out")])
            self.assertEqual(code,2)
            report=json.loads((Path(tmp)/"out/report.json").read_text())
            self.assertEqual(report["status"],"BLOCKED");self.assertFalse(report["production_go"])

    def test_plan_is_not_a_pass_and_runs_no_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"root";root.mkdir();SnapshotTests().fixture(root)
            with patch.object(release_tests,"ROOT",root), patch("release_tests.subprocess.run") as call:
                code=release_tests.main(["--plan","--output",str(Path(tmp)/"out")])
            self.assertEqual(code,0);call.assert_not_called()
            self.assertEqual(json.loads((Path(tmp)/"out/report.json").read_text())["status"],"PLAN_ONLY")


class DbSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location("isolated_guard",ROOT/"backend/scripts/isolated_test_guard.py")
        cls.guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.guard)

    def test_normal_app_target_rejected_even_with_marker_env(self):
        with patch.dict(os.environ,{"RELEASE_TEST_RUN_ID":PROJECT}), self.assertRaises(RuntimeError):
            self.guard.validate_test_target("postgresql://workapp:pw@db:5432/workapp")

    def test_missing_run_marker_env_rejected(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(RuntimeError):
            self.guard.validate_test_target("postgresql://workapp:pw@test-db:5432/munkalap_test")

    def test_database_override_query_rejected(self):
        with patch.dict(os.environ,{"RELEASE_TEST_RUN_ID":PROJECT}),self.assertRaises(RuntimeError):
            self.guard.validate_test_target("postgresql://x:pw@test-db:5432/munkalap_test?host=production")

    def test_test_target_is_accepted_for_marker_check(self):
        with patch.dict(os.environ,{"RELEASE_TEST_RUN_ID":PROJECT}):
            self.assertEqual(self.guard.validate_test_target("postgresql://x:pw@test-db:5432/munkalap_test"),PROJECT)


if __name__ == "__main__":
    unittest.main()
