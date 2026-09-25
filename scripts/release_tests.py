#!/usr/bin/env python3
"""Isolated, fail-closed release-test launcher. Python >= 3.10 + Docker Compose v2.

Never reads .env/.env.production and never merges production Compose files.
Exit 0: requested test scope passed (not production approval).
Exit 1: tests failed. Exit 2: missing prerequisites/build/setup/cleanup blocked.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from release_support import (build_model, clean_environment, copy_snapshot, image_tags,
    load_manifest, redact, runtime_model, validate_runtime_model)

ROOT = Path(__file__).resolve().parents[1]


class CommandFailed(RuntimeError):
    pass


class Runner:
    def __init__(self, output, env, secrets_to_hide):
        self.output, self.env, self.hidden = Path(output), env, list(secrets_to_hide)
        self.results = []

    def command(self, name, argv, *, cwd=None, timeout=900, required=True):
        started = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=cwd, env=self.env, text=True, encoding="utf-8",
                errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            code, text = result.returncode, result.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
            text = str(exc)
        safe = redact(text, self.hidden)
        path = self.output / (f"{len(self.results)+1:02d}-{name}.log")
        path.write_text(safe, encoding="utf-8")
        row = {"name": name, "exit_code": code, "status": "PASS" if code == 0 else "FAIL",
               "duration_seconds": round(time.monotonic()-started, 3), "log": path.name,
               "command": redact(json.dumps(argv), self.hidden)}
        self.results.append(row)
        print(f"[{row['status']}] {name}; log={path.name}", flush=True)
        if code and required:
            raise CommandFailed(f"{name} failed (exit {code}); see {path.name}")
        return code, text


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def parse_image(output, source_digest):
    data = json.loads(output)
    if len(data) != 1 or not data[0].get("Id", "").startswith("sha256:"):
        raise ValueError("Unexpected docker image inspect output")
    image = data[0]
    if image.get("Config", {}).get("Labels", {}).get("hu.lunait.release.source-sha256") != source_digest:
        raise ValueError("Image not built from this source snapshot")
    return image["Id"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "unit", "pg"), default="all")
    parser.add_argument("--plan", action="store_true", help="Validate source/isolation and write a plan only; NOT a test PASS")
    parser.add_argument("--output", type=Path, help="New evidence directory (must not already exist)")
    args = parser.parse_args(argv)
    project = "munkalap-test-" + uuid.uuid4().hex[:12]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or ROOT / "test-results" / (stamp + "-" + project)
    output = output.resolve()
    if output.exists():
        print("Evidence directory already exists; choose a new path", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    credentials = {key: secrets.token_hex(24) for key in ("admin", "app", "migrate", "key", "mfa")}
    credentials["bootstrap"] = "Test!" + secrets.token_hex(24) + "A9"
    runner = Runner(output, clean_environment(), credentials.values())
    report = {"format": 1, "project": project, "scope": args.suite, "status": "BLOCKED", "production_go": False,
              "started_at_utc": stamp, "stages": runner.results,
              "not_in_scope": ["VPS/TLS/public exposure", "malware scanner / Firebase / offsite backup",
                  "Android device E2E", "PostgreSQL MFA/refresh/signature concurrency tests", "signed-document integrity fixes", "current CVE/security scan"],
              "known_limitations": ["Backend API suite remains SQLite; PostgreSQL lifecycle is a separate real-DB suite",
                  "Mobile has no package-lock.json: Node unit tests only, no npm/Android build claim",
                  "Python transitive/base-image versions are recorded, not newly locked in this step",
                  "Backup suites are unit/source tests, not physical backup/restore acceptance"]}
    compose = None
    runtime_started = False
    exit_code = 2
    # Keep the generated credentials/config only in a temporary directory. No .env is copied.
    with tempfile.TemporaryDirectory(prefix="munkalap-release-test-") as temporary:
        temp = Path(temporary)
        try:
            manifest, source_digest = load_manifest(ROOT)
            report.update(version=manifest["version"], source_manifest_sha256=source_digest)
            snapshot = temp / "source"
            copy_snapshot(ROOT, snapshot, manifest)
            tags = image_tags(project, manifest["version"])
            plan = runtime_model(project, tags, credentials)
            validate_runtime_model(plan, project, tags)
            write_json(output / "test-plan.redacted.json", json.loads(redact(json.dumps(plan), credentials.values())))
            if args.plan:
                report["status"] = "PLAN_ONLY"
                exit_code = 0
            else:
                runner.command("docker-version", ["docker", "version"], timeout=30)
                runner.command("compose-version", ["docker", "compose", "version"], timeout=30)
                _, old = runner.command("project-collision-check", ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project], timeout=30)
                if old.strip():
                    raise ValueError("Refusing an existing test project")
                empty_env = temp / "empty.env"
                empty_env.write_text("", encoding="utf-8")
                build_path = temp / "build.json"
                write_json(build_path, build_model(snapshot, tags, source_digest))
                base = ["docker", "compose", "--ansi", "never", "--project-name", project, "--project-directory", str(temp), "--env-file", str(empty_env)]
                build = base + ["-f", str(build_path)]
                runner.command("build-compose-config", build + ["config", "--quiet"], cwd=temp, timeout=30)
                # Parent release image is built BEFORE the test-only image, never concurrently.
                runner.command("build-release-images", build + ["build", "backend", "db", "frontend", "backup-agent", "backup-runner"], cwd=temp, timeout=1800)
                runner.command("build-test-tools", build + ["build", "python-tests", "node-tests"], cwd=temp, timeout=900)
                images = {}
                for kind, tag in tags.items():
                    _, text = runner.command("image-" + kind, ["docker", "image", "inspect", tag], timeout=30)
                    images[kind] = parse_image(text, source_digest)
                report["image_ids"] = images
                model = runtime_model(project, images, credentials)
                validate_runtime_model(model, project, images)
                runtime_path = temp / "runtime.json"
                write_json(runtime_path, model)
                compose = base + ["-f", str(runtime_path)]
                _, effective = runner.command("runtime-compose-config", compose + ["config", "--format", "json"], cwd=temp, timeout=30)
                validate_runtime_model(json.loads(effective), project, images)

                def run(name, service, *command, entrypoint=None, required=True, timeout=900):
                    call = compose + ["run", "--rm", "--no-deps", "-T", "--pull", "never"]
                    if entrypoint:
                        call += ["--entrypoint", entrypoint]
                    return runner.command(name, call + [service, *command], cwd=temp, required=required, timeout=timeout)

                # Every environment-dependent test follows successful isolation validation.
                runtime_started = True
                failures = []
                run("python-environment", "python-tests", "-m", "pip", "freeze", entrypoint="python")
                if args.suite in ("all", "unit"):
                    for name, path, config in (
                        ("backend-tests", "/suite/backend/tests", "/suite/backend/pytest.ini"),
                        ("backup-unit-tests", "/suite/backup_agent/tests", "/suite/deploy/testing/pytest.ini"),
                        ("runner-unit-tests", "/suite/backup_runner/tests", "/suite/deploy/testing/pytest.ini")):
                        code, _ = run(name, "python-tests", "-m", "pytest", "-c", config, "-q", "-p", "no:cacheprovider", "--basetemp=/tmp/pytest", path, entrypoint="python", required=False, timeout=1800)
                        failures.append(code)
                    code, _ = run("release-harness-tests", "python-tests", "-m", "unittest", "discover", "-s", "/suite/tests/release", "-v", entrypoint="python", required=False)
                    failures.append(code)
                    # Discover files in the frozen snapshot, not by shell glob expansion.
                    for group in ("frontend", "mobile"):
                        paths = sorted("/suite/" + p.relative_to(snapshot).as_posix() for p in (snapshot / group / "tests").glob("*.test.js"))
                        if not paths:
                            raise ValueError("Empty Node suite: " + group)
                        code, _ = run(group + "-node-tests", "node-tests", *paths, required=False)
                        failures.append(code)
                if args.suite in ("all", "pg"):
                    for scenario in ("fresh", "upgrade-0026"):
                        runner.command(scenario + "-db-start", compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "test-db"], cwd=temp, timeout=150)
                        run(scenario + "-marker", "pg-checks", "marker")
                        if scenario != "fresh":
                            run("legacy-schema", "legacy-migrate", "upgrade", "0026_location_active_status")
                            run("legacy-fixture", "pg-checks", "legacy-fixture")
                        run(scenario + "-provision", "db-role-provisioner")
                        run(scenario + "-migrate", "migrate")
                        # Separate process/connection proves COMMIT, not just Alembic log lines.
                        run(scenario + "-committed-head", "pg-checks", "assert-head")
                        run(scenario + "-runtime-identity", "pg-checks", "identities")
                        run(scenario + "-runtime-privileges", "pg-checks", "privileges")
                        if scenario != "fresh":
                            run("legacy-preservation", "pg-checks", "verify-legacy")
                        run(scenario + "-snapshot", "pg-checks", "snapshot")
                        run(scenario + "-provision-again", "db-role-provisioner")
                        run(scenario + "-migrate-again", "migrate")
                        run(scenario + "-idempotency", "pg-checks", "compare-snapshot")
                        run(scenario + "-serial-identity-ownership", "pg-checks", "role-regression")
                        runner.command(scenario + "-web-start", compose + ["up", "-d", "--no-build", "--no-deps", "backend", "frontend"], cwd=temp, timeout=90)
                        run(scenario + "-web-smoke", "pg-checks", "smoke", timeout=120)
                        runner.command(scenario + "-web-restart", compose + ["restart", "backend", "frontend"], cwd=temp, timeout=90)
                        run(scenario + "-web-restart-smoke", "pg-checks", "smoke", timeout=120)
                        runner.command(scenario + "-logs", compose + ["logs", "--no-color", "--tail=200"], cwd=temp, timeout=30, required=False)
                        # No volumes exist in this model; database data is disposable tmpfs.
                        runner.command(scenario + "-cleanup", compose + ["down", "--remove-orphans"], cwd=temp, timeout=90)
                report["status"] = "FAIL" if any(failures) else "PASS_REQUESTED_SCOPE"
                exit_code = 1 if any(failures) else 0
        except (CommandFailed, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
            report["error"] = redact(str(exc), credentials.values())
            print("[BLOCKED] " + report["error"], file=sys.stderr)
        except KeyboardInterrupt:
            report["error"] = "Interrupted; cleanup requested"
        finally:
            if compose is not None and runtime_started:
                runner.command("final-logs", compose + ["logs", "--no-color", "--tail=200"], cwd=temp, timeout=30, required=False)
                code, _ = runner.command("final-cleanup", compose + ["down", "--remove-orphans"], cwd=temp, timeout=90, required=False)
                if code:
                    report["status"] = "BLOCKED_CLEANUP"
                    report["cleanup_project"] = project
                    exit_code = 2
            report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(output / "report.json", report)
    print("Result: " + report["status"])
    print("Evidence: " + str(output))
    print("This is a test-baseline result, NOT a VPS/security/Android production approval.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
