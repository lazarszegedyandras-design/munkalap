from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _secret_env(name: str, file_name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    path = os.getenv(file_name, "").strip()
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


RUNNER_URL = os.getenv("BACKUP_RUNNER_URL", "http://backup-runner:8091").rstrip("/")
RUNNER_TOKEN = _secret_env("BACKUP_RUNNER_TOKEN", "BACKUP_RUNNER_TOKEN_FILE")


def request(method: str, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 120) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RUNNER_URL + path,
        data=body,
        method=method,
        headers={
            "X-Backup-Runner-Token": RUNNER_TOKEN,
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            detail = ""
        raise RuntimeError(f"Backup runner request failed: HTTP {exc.code}; {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Backup runner is unavailable: {type(exc).__name__}: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Backup runner returned an invalid response")
    return result


def get(path: str, *, timeout: float = 120) -> dict[str, Any]:
    return request("GET", path, timeout=timeout)


def post(path: str, payload: dict[str, Any] | None = None, *, timeout: float = 120) -> dict[str, Any]:
    return request("POST", path, payload or {}, timeout=timeout)
