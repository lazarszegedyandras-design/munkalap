#!/usr/bin/env python3
"""Verify built/running release image identities from `compose config --format json`.

Read configuration from stdin, but NEVER print/save environment or secrets.
This read-only check does not start services, run migrations, or connect to DB.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

GROUP = ("backend", "migrate", "db-role-provisioner", "runtime-permissions", "push-worker")
OWNED = GROUP + ("db", "frontend", "backup-agent", "backup-runner")


def execute(args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        # Docker may include config values in error messages. Do not relay them.
        raise RuntimeError("Docker image/container inspection failed")
    return result.stdout


def verify(model, version, *, running=False, call=execute):
    services = model["services"]
    reference = services["backend"].get("image")
    if not reference or any(services[name].get("image") != reference for name in GROUP):
        raise RuntimeError("Backend/migrate/provisioner/runtime-permissions/push-worker must share one image reference")
    expected = {}
    for name in OWNED:
        ref = services[name].get("image")
        if not ref or not ref.endswith(":" + version):
            raise RuntimeError("Wrong release image tag for service: " + name)
        data = json.loads(call(["image", "inspect", "--format", '{{json .}}', ref]))
        if data.get("Config", {}).get("Labels", {}).get("hu.lunait.release.version") != version:
            raise RuntimeError("Missing/wrong release build label: " + name)
        expected[name] = {"reference": ref, "image_id": data["Id"]}
    if len({expected[name]["image_id"] for name in GROUP}) != 1:
        raise RuntimeError("Mixed backend image IDs")
    if running:
        project = model.get("name")
        if not project:
            raise RuntimeError("Effective Compose project name missing")
        for name in OWNED:
            containers = call(["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project,
                "--filter", "label=com.docker.compose.service=" + name,
                "--filter", "label=com.docker.compose.oneoff=False"]).split()
            if not containers:
                raise RuntimeError("Missing release container: " + name)
            for container in containers:
                actual = call(["inspect", "--format", "{{.Image}}", container]).strip()
                if actual != expected[name]["image_id"]:
                    raise RuntimeError("Stale running/completed image for service: " + name)
    return expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--running", action="store_true")
    parser.add_argument("--lock", type=Path, help="Require exact IDs from a promoted full test run")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        version = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
        result = verify(json.load(sys.stdin), version, running=args.running)
        if args.lock:
            lock = json.loads(args.lock.read_text(encoding="utf-8"))
            from release_support import load_manifest
            _, current_digest = load_manifest(Path(__file__).resolve().parents[1])
            if lock.get("source_manifest_sha256") != current_digest:
                raise RuntimeError("Source manifest changed after testing")
            if lock.get("version") != version:
                raise RuntimeError("Wrong image lock version")
            for name, actual in result.items():
                kind = "backend" if name in GROUP else name
                if lock["images"][kind] != actual:
                    raise RuntimeError("Image no longer matches tested ID: " + name)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
        print("Release image identities PASS" + (" (containers checked)" if args.running else " (built images checked)"))
        return 0
    except (KeyError, ValueError, RuntimeError, OSError):
        print("Release image identity check FAILED; rebuild the release and verify APP_VERSION (no secrets printed)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
