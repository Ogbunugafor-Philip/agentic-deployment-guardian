import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main

SECRET = "test-webhook-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def client(monkeypatch):
    # Avoid DB/Redis/Celery during the request lifecycle.
    monkeypatch.setattr(main, "create_tables", lambda *a, **k: None)
    monkeypatch.setattr(main, "_persist_incident", lambda *a, **k: None)
    with TestClient(main.app) as c:
        yield c


def test_health_is_open(client):
    resp = client.get("/health")
    assert resp.status_code in (200, 503)  # open without auth


def test_incidents_requires_jwt(client):
    assert client.get("/incidents").status_code == 401


def test_token_then_access(client, monkeypatch):
    monkeypatch.setattr(main, "recent_incidents", lambda limit=20: [])
    tok = client.post("/token", data={"username": "guardian", "password": "test-api-password"})
    assert tok.status_code == 200
    jwt_token = tok.json()["access_token"]
    ok = client.get("/incidents", headers={"Authorization": f"Bearer {jwt_token}"})
    assert ok.status_code == 200
    assert ok.json()["count"] == 0


def test_webhook_valid_signature(client):
    body = json.dumps({"job_id": "1", "conclusion": "failure",
                       "repository": {"owner": "o", "name": "r"}}).encode()
    resp = client.post("/webhook/github", data=body,
                       headers={"X-Hub-Signature-256": _sign(body),
                                "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


def test_webhook_invalid_signature(client):
    body = b'{"job_id":"1"}'
    resp = client.post("/webhook/github", data=body,
                       headers={"X-Hub-Signature-256": "sha256=deadbeef",
                                "Content-Type": "application/json"})
    assert resp.status_code == 401


def test_webhook_missing_signature(client):
    resp = client.post("/webhook/github", data=b"{}",
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 401
