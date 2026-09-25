from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_VERSION = "0.31.0"
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def _read_version() -> str:
    environment_version = os.getenv("APP_VERSION", "").strip()
    if environment_version:
        return environment_version

    current = Path(__file__).resolve()
    candidates = [
        Path("/app/VERSION"),
        current.parents[2] / "VERSION",  # projektgyökér helyi futtatáskor
        current.parents[1] / "VERSION",  # opcionális backend-specifikus másolat
    ]
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return DEFAULT_VERSION


APP_VERSION = _read_version()


def semantic_version_parts(version: str = APP_VERSION) -> dict[str, object]:
    match = SEMVER_RE.fullmatch(version)
    if not match:
        return {
            "major": None,
            "minor": None,
            "patch": None,
            "prerelease": None,
            "build": None,
        }
    groups = match.groupdict()
    return {
        "major": int(groups["major"]),
        "minor": int(groups["minor"]),
        "patch": int(groups["patch"]),
        "prerelease": groups["prerelease"],
        "build": groups["build"],
    }
