#!/usr/bin/env python3
"""Tag the EXACT images from a passing isolated run for local/staging deployment.

No image rebuild, service start, database write, or production approval occurs.
The generated lock can be checked immediately before/after deployment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

from release_support import load_manifest

IMAGE_NAMES = {"backend": "munkalap-backend", "db": "munkalap-postgres-pgbackrest",
    "frontend": "munkalap-frontend", "backup-agent": "munkalap-backup-agent", "backup-runner": "munkalap-backup-runner"}


def validate_report(report, version, digest):
    if report.get("status") != "PASS_REQUESTED_SCOPE" or report.get("scope") != "all":
        raise ValueError("Only a complete --suite all PASS can be promoted")
    if report.get("version") != version or report.get("source_manifest_sha256") != digest:
        raise ValueError("Test report does not match this verified release source")
    names = {stage.get("name") for stage in report.get("stages", []) if stage.get("exit_code") == 0}
    required = {"backend-tests", "backup-unit-tests", "runner-unit-tests", "release-harness-tests",
        "frontend-node-tests", "mobile-node-tests", "fresh-committed-head", "upgrade-0026-committed-head",
        "legacy-preservation", "fresh-idempotency", "upgrade-0026-idempotency",
        "fresh-runtime-privileges", "upgrade-0026-runtime-privileges",
        "fresh-web-restart-smoke", "upgrade-0026-web-restart-smoke", "final-cleanup"}
    if not required.issubset(names):
        raise ValueError("Required successful stages are missing from report")
    for kind in IMAGE_NAMES:
        if not report.get("image_ids", {}).get(kind, "").startswith("sha256:"):
            raise ValueError("Missing content-addressed image: " + kind)


def docker(*args):
    p = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if p.returncode:
        raise RuntimeError("Docker image verification/tagging failed; no services were started")
    return p.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    try:
        manifest,digest=load_manifest(root)
        report=json.loads(args.report.read_text(encoding="utf-8"))
        version=manifest["version"]
        validate_report(report,version,digest)
        mapping={}
        # Inspect every immutable ID BEFORE tagging any image. No pulls allowed.
        for kind,name in IMAGE_NAMES.items():
            ident=report["image_ids"][kind]
            inspected=json.loads(docker("image","inspect",ident))[0]
            labels=inspected.get("Config",{}).get("Labels",{})
            if inspected.get("Id")!=ident or labels.get("hu.lunait.release.source-sha256")!=digest or labels.get("hu.lunait.release.version")!=version:
                raise ValueError("Image source identity differs from test evidence: "+kind)
            mapping[kind]={"reference":name+":"+version,"image_id":ident}
        for value in mapping.values():
            docker("tag",value["image_id"],value["reference"])
        lock={"format":1,"version":version,"source_manifest_sha256":digest,"images":mapping,"production_go":False}
        (root/"release-images.lock.json").write_text(json.dumps(lock,indent=2)+"\n",encoding="utf-8")
        print("Exact tested images tagged; release-images.lock.json written. No services started.")
        print("Use the local launcher with -SkipBuild; rebuilding invalidates this evidence.")
        print("This is NOT a public VPS or digital-signature production approval.")
        return 0
    except (OSError,KeyError,ValueError,RuntimeError):
        print("Promotion refused. Check full test status, source manifest and local Docker images.",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
