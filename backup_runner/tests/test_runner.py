from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

import runner


client = TestClient(runner.app, raise_server_exceptions=False)
HEADERS = {"X-Backup-Runner-Token": "runner-test-token"}


def setup_function():
    runner.RUNNER_TOKEN = "runner-test-token"


def test_authentication_is_required_and_constant_endpoint_is_private():
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"X-Backup-Runner-Token": "wrong"}).status_code == 401
    assert client.get("/health", headers=HEADERS).status_code == 200


def test_no_generic_command_endpoint_and_extra_command_field_is_rejected():
    assert client.post("/run", headers=HEADERS, json={"command": "docker", "args": ["ps"]}).status_code == 404
    response = client.post(
        "/services/backend/stop",
        headers=HEADERS,
        json={"timeout_seconds": 30, "command": "docker exec anything"},
    )
    assert response.status_code == 422


def test_unknown_service_and_invalid_restore_inputs_are_rejected():
    assert client.get("/services/arbitrary", headers=HEADERS).status_code == 422
    assert client.post(
        "/database/restore", headers=HEADERS,
        json={"label": "../../etc/passwd", "stop_lsn": "0/123ABC"},
    ).status_code == 422
    assert client.post(
        "/database/restore", headers=HEADERS,
        json={"label": "20260910-120000F", "stop_lsn": "not-an-lsn"},
    ).status_code == 422


def test_repository_path_traversal_is_rejected_before_docker_call():
    response = client.post(
        "/images/export",
        headers=HEADERS,
        json={"services": ["backend"], "destination": "../outside.tar"},
    )
    assert response.status_code == 422


def test_allowlisted_service_metadata_route(monkeypatch):
    monkeypatch.setattr(
        runner,
        "service_metadata",
        lambda service: {"service": service, "image_reference": "safe:1", "image_id": "sha256:1", "running": True},
    )
    response = client.get("/services/backend", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["service"] == "backend"


def test_subprocess_is_always_called_with_an_argument_list(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["docker", "version"])
    assert result.stdout == "ok"
    assert observed["command"] == ["docker", "version"]
    assert isinstance(observed["command"], list)
    assert observed["kwargs"]["check"] is False


def test_error_response_does_not_echo_runner_secret(monkeypatch):
    def failed(_service):
        raise RuntimeError("ordinary failure")

    monkeypatch.setattr(runner, "service_metadata", failed)
    response = client.get("/services/backend", headers=HEADERS)
    assert "runner-test-token" not in response.text
