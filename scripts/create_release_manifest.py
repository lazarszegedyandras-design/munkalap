"""Create an isolated release-test manifest from reviewed Git source files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from release_support import MANIFEST_NAME, safe_source_path


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "VERSION", "CHANGELOG.md", "mobile/package.json", ".gitignore", ".dockerignore",
    ".env.example", ".env.production.example", "docker-compose.yml",
    "docker-compose.dev.yml", "docker-compose.production.yml", "compose.yaml",
    "compose.override.yaml", "acceptance-backup-restore.ps1",
    "backup-munkalap-app.ps1", "restore-munkalap-app.ps1",
    "start-v0.30.0-hotfix.ps1",
}
SOURCE_PREFIXES = (
    "backend/", "backup_agent/", "backup_runner/", "database/",
    "deploy/", "frontend/", "mobile/",
    "scripts/", "tests/release/",
)


def main() -> int:
    output = ROOT / MANIFEST_NAME
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing {MANIFEST_NAME}")

    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "-z"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\0")

    files = {}
    for name in tracked:
        if not name or (name not in ROOT_FILES and not name.startswith(SOURCE_PREFIXES)):
            continue
        relative = safe_source_path(name)
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Source is missing or is a symlink: {name}")
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    if not files or not ROOT_FILES.issubset(files):
        raise ValueError("Required release-test source is missing")
    for prefix in SOURCE_PREFIXES:
        if not any(name.startswith(prefix) for name in files):
            raise ValueError(f"Required release-test source group is missing: {prefix}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = {"format": 1, "version": version, "files": dict(sorted(files.items()))}
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Created {MANIFEST_NAME} from {len(files)} tracked source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
