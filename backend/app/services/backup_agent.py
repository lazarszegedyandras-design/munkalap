from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from ..config import get_settings


def _agent_request(method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    settings = get_settings()
    if not settings.backup_agent_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A backup-agent nincs konfigurálva (BACKUP_AGENT_TOKEN hiányzik)",
        )
    url = settings.backup_agent_url.rstrip("/") + path
    try:
        response = httpx.request(
            method,
            url,
            json=json,
            params=params,
            headers={"X-Backup-Agent-Token": settings.backup_agent_token},
            timeout=settings.backup_agent_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A backup-agent jelenleg nem érhető el",
        ) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        raise HTTPException(status_code=response.status_code, detail=detail or "Backup-agent hiba")
    return payload


def agent_get(path: str, *, params: dict[str, Any] | None = None) -> Any:
    return _agent_request("GET", path, params=params)


def agent_post(path: str, payload: dict[str, Any] | None = None) -> Any:
    return _agent_request("POST", path, json=payload or {})


def agent_put(path: str, payload: dict[str, Any]) -> Any:
    return _agent_request("PUT", path, json=payload)
