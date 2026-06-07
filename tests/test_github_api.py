import pytest

import app.github_api as gh


class FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_job_logs_success(monkeypatch):
    monkeypatch.setattr(gh.requests, "get", lambda *a, **k: FakeResp(200, "line1\nline2"))
    assert gh.fetch_job_logs("o", "r", 123) == "line1\nline2"


def test_fetch_job_logs_strips_bom(monkeypatch):
    monkeypatch.setattr(gh.requests, "get", lambda *a, **k: FakeResp(200, "﻿hello"))
    assert gh.fetch_job_logs("o", "r", 1) == "hello"


def test_fetch_job_logs_404(monkeypatch):
    monkeypatch.setattr(gh.requests, "get", lambda *a, **k: FakeResp(404))
    with pytest.raises(gh.LogsNotFound):
        gh.fetch_job_logs("o", "r", 999)


def test_get_last_successful_deploy_sha(monkeypatch):
    class R(FakeResp):
        def json(self):
            return {"workflow_runs": [
                {"name": "Deploy Agentic Deployment Guardian", "conclusion": "failure", "head_sha": "bad"},
                {"name": "Deploy Agentic Deployment Guardian", "conclusion": "success", "head_sha": "good123"},
            ]}
    monkeypatch.setattr(gh.requests, "get", lambda *a, **k: R(200))
    assert gh.get_last_successful_deploy_sha("o", "r") == "good123"
