#!/usr/bin/env python3
"""A projektverzió egységes frissítése és ellenőrzése.

Használat:
    python scripts/set_version.py 0.6.0
    python scripts/set_version.py --check

A frissítés módosítja a gyökér VERSION fájlt, a backend alapértelmezett
verzióját, a frontend package.json és package-lock.json verziómezőit, a
backup-agent alapverzióját, a Docker Compose APP_VERSION alapértékeit, az
acceptance runner, a mobil kliens, a production Compose/preflight és az env minták verzióját. A CHANGELOG.md tartalmát
szándékosan nem generálja automatikusan; a kiadás leírását kézzel kell rögzíteni.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def update_package_file(path: Path, version: str) -> None:
    data = load_json(path)
    data["version"] = version
    if path.name == "package-lock.json":
        root_package = data.get("packages", {}).get("")
        if isinstance(root_package, dict):
            root_package["version"] = version
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_backend_default_version(version: str) -> None:
    path = ROOT / "backend" / "app" / "version.py"
    source = path.read_text(encoding="utf-8")
    updated, count = re.subn(r'DEFAULT_VERSION = "[^"]+"', f'DEFAULT_VERSION = "{version}"', source, count=1)
    if count != 1:
        fail("A backend alapértelmezett verziója nem frissíthető")
    path.write_text(updated, encoding="utf-8")


def update_text_version(path: Path, pattern: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, source, flags=re.MULTILINE)
    if count < 1:
        fail(f"A verzió nem frissíthető ebben a fájlban: {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")



def android_version_code(version: str) -> int:
    core = version.split("-", 1)[0].split("+", 1)[0]
    major, minor, patch = (int(item) for item in core.split("."))
    return major * 1_000_000 + minor * 1_000 + patch


def check_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER_RE.fullmatch(version):
        fail(f"A VERSION fájl érvénytelen szemantikus verziót tartalmaz: {version!r}")

    package_version = load_json(ROOT / "frontend" / "package.json").get("version")
    lock_data = load_json(ROOT / "frontend" / "package-lock.json")
    lock_version = lock_data.get("version")
    lock_root_version = lock_data.get("packages", {}).get("", {}).get("version")
    backend_source = (ROOT / "backend" / "app" / "version.py").read_text(encoding="utf-8")
    backend_match = re.search(r'DEFAULT_VERSION = "([^"]+)"', backend_source)
    backend_version = backend_match.group(1) if backend_match else None
    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose_versions = re.findall(r"\$\{APP_VERSION:-([^}]+)\}", compose_source)
    env_source = (ROOT / ".env.example").read_text(encoding="utf-8")
    env_match = re.search(r"^APP_VERSION=(.+)$", env_source, flags=re.MULTILINE)
    env_version = env_match.group(1).strip() if env_match else None
    agent_source = (ROOT / "backup_agent" / "agent.py").read_text(encoding="utf-8")
    agent_match = re.search(r'APP_VERSION = os\.environ\.get\("APP_VERSION", "([^"]+)"\)', agent_source)
    agent_version = agent_match.group(1) if agent_match else None
    acceptance_source = (ROOT / "acceptance-backup-restore.ps1").read_text(encoding="utf-8")
    acceptance_match = re.search(r"^APP_VERSION=(.+)$", acceptance_source, flags=re.MULTILINE)
    acceptance_version = acceptance_match.group(1).strip() if acceptance_match else None
    mobile_version = load_json(ROOT / "mobile" / "package.json").get("version")
    mobile_env_source = (ROOT / "mobile" / ".env.example").read_text(encoding="utf-8")
    mobile_env_match = re.search(r"^VITE_APP_VERSION=(.+)$", mobile_env_source, flags=re.MULTILINE)
    mobile_env_version = mobile_env_match.group(1).strip() if mobile_env_match else None
    prod_env_source = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    prod_env_match = re.search(r"^APP_VERSION=(.+)$", prod_env_source, flags=re.MULTILINE)
    prod_env_version = prod_env_match.group(1).strip() if prod_env_match else None
    prod_compose_source = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    prod_compose_versions = re.findall(r"\$\{APP_VERSION:-([^}]+)\}", prod_compose_source)
    preflight_source = (ROOT / "deploy" / "vps" / "preflight-production.sh").read_text(encoding="utf-8")
    preflight_match = re.search(r'APP_VERSION:-}\" = \"([^\"]+)\"', preflight_source)
    preflight_version = preflight_match.group(1) if preflight_match else None
    values = {
        "VERSION": version,
        "backend/app/version.py": backend_version,
        "frontend/package.json": package_version,
        "frontend/package-lock.json": lock_version,
        "frontend/package-lock.json packages['']": lock_root_version,
        "backup_agent/agent.py": agent_version,
        "acceptance-backup-restore.ps1": acceptance_version,
        ".env.example": env_version,
        ".env.production.example": prod_env_version,
        "mobile/package.json": mobile_version,
        "mobile/.env.example": mobile_env_version,
        "deploy/vps/preflight-production.sh": preflight_version,
    }
    mismatches = {name: value for name, value in values.items() if value != version}
    if not compose_versions or any(value != version for value in compose_versions):
        mismatches["docker-compose.yml APP_VERSION defaults"] = compose_versions
    if not prod_compose_versions or any(value != version for value in prod_compose_versions):
        mismatches["docker-compose.production.yml APP_VERSION defaults"] = prod_compose_versions
    canonical = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    if canonical != compose_source:
        mismatches["compose.yaml vs docker-compose.yml"] = "different"
    if mismatches:
        details = ", ".join(f"{name}={value!r}" for name, value in mismatches.items())
        fail(f"A verziók nincsenek szinkronban. Elvárt: {version}. Eltérések: {details}")
    print(f"A verziók szinkronban vannak: {version}")


def main() -> None:
    if len(sys.argv) != 2:
        fail("Használat: python scripts/set_version.py <X.Y.Z> | --check")
    argument = sys.argv[1].strip()
    if argument == "--check":
        check_version()
        return
    if not SEMVER_RE.fullmatch(argument):
        fail("Érvénytelen szemantikus verzió. Példa: 0.6.0")

    (ROOT / "VERSION").write_text(argument + "\n", encoding="utf-8")
    update_backend_default_version(argument)
    update_package_file(ROOT / "frontend" / "package.json", argument)
    update_package_file(ROOT / "frontend" / "package-lock.json", argument)
    update_text_version(
        ROOT / "backup_agent" / "agent.py",
        r'APP_VERSION = os\.environ\.get\("APP_VERSION", "[^"]+"\)',
        f'APP_VERSION = os.environ.get("APP_VERSION", "{argument}")',
    )
    update_text_version(
        ROOT / "docker-compose.yml",
        r"\$\{APP_VERSION:-[^}]+\}",
        f"${{APP_VERSION:-{argument}}}",
    )
    update_text_version(
        ROOT / "acceptance-backup-restore.ps1",
        r"^APP_VERSION=.*$",
        f"APP_VERSION={argument}",
    )
    update_text_version(ROOT / ".env.example", r"^APP_VERSION=.*$", f"APP_VERSION={argument}")
    update_text_version(ROOT / ".env.production.example", r"^APP_VERSION=.*$", f"APP_VERSION={argument}")
    update_package_file(ROOT / "mobile" / "package.json", argument)
    update_text_version(ROOT / "mobile" / ".env.example", r"^VITE_APP_VERSION=.*$", f"VITE_APP_VERSION={argument}")
    update_text_version(
        ROOT / "mobile" / "src" / "services" / "device.js",
        r"VITE_APP_VERSION \|\| '[^']+'",
        f"VITE_APP_VERSION || '{argument}'",
    )
    signing_path = ROOT / "mobile" / "scripts" / "release-signing.gradle"
    signing_source = signing_path.read_text(encoding="utf-8")
    signing_source = re.sub(r"env\['MUNKALAP_VERSION_NAME'\] \?: '[^']+'", f"env['MUNKALAP_VERSION_NAME'] ?: '{argument}'", signing_source, count=1)
    signing_source = re.sub(r"env\['MUNKALAP_VERSION_CODE'\] \?: '[0-9]+'", f"env['MUNKALAP_VERSION_CODE'] ?: '{android_version_code(argument)}'", signing_source, count=1)
    signing_path.write_text(signing_source, encoding="utf-8")
    update_text_version(
        ROOT / "docker-compose.production.yml",
        r"\$\{APP_VERSION:-[^}]+\}",
        f"${{APP_VERSION:-{argument}}}",
    )
    preflight_path = ROOT / "deploy" / "vps" / "preflight-production.sh"
    preflight_source = preflight_path.read_text(encoding="utf-8")
    preflight_source, count = re.subn(
        r'\[ "\$\{APP_VERSION:-\}" = "[^"]+" \] \|\| fail "APP_VERSION must be [^"]+"',
        f'[ "${{APP_VERSION:-}}" = "{argument}" ] || fail "APP_VERSION must be {argument}"',
        preflight_source,
        count=1,
    )
    if count != 1:
        fail("A production preflight verziója nem frissíthető")
    preflight_path.write_text(preflight_source, encoding="utf-8")

    (ROOT / "compose.yaml").write_bytes((ROOT / "docker-compose.yml").read_bytes())

    print(f"A projekt verziója frissítve: {argument}")
    print("Következő lépés: egészítsd ki a CHANGELOG.md fájlt, majd készíts Git taget: v" + argument)


if __name__ == "__main__":
    main()
