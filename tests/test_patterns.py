import app.patterns as patterns
from app.patterns import _suggested_fix, classify_label, match_for, pattern_key, recompute_patterns


def test_pattern_key_normalizes():
    assert pattern_key("Run Tests", 1) == "run tests|1"
    assert pattern_key("Build", None) == "build|na"


def test_classify_label_env_config():
    label = classify_label("Write .env", "Why it failed: missing secret values")
    assert label == "Repeated env/config failure"


def test_classify_label_test():
    assert classify_label("Run tests", "AssertionError") == "Recurring test failure"


def test_classify_label_service_crash():
    assert classify_label("Start app", "container health check failed") == "Repeated service crash"


def test_classify_label_fallback():
    assert classify_label("Weird step", "no idea").startswith("Recurring failure at step")


def test_suggested_fix_extraction():
    rc = "Failure point: x\nWhy it failed: y\nSuggested fix: Add the missing secret."
    assert _suggested_fix(rc) == "Add the missing secret."
    assert _suggested_fix("no fix here") == ""


def test_recompute_patterns(monkeypatch):
    groups = [{
        "failed_step": "Run tests", "exit_code": 1, "occurrence_count": 3,
        "first_seen": "t0", "last_seen": "t1",
        "latest_root_cause": "Suggested fix: fix the test",
    }]
    calls = []
    monkeypatch.setattr(patterns, "fetch_recurring_groups", lambda min_count=2: groups)
    monkeypatch.setattr(patterns, "upsert_failure_pattern", lambda **kw: calls.append(kw))
    assert recompute_patterns() == 1
    assert calls[0]["pattern_key"] == "run tests|1"
    assert calls[0]["pattern_label"] == "Recurring test failure"
    assert calls[0]["suggested_fix"] == "fix the test"


def test_match_for(monkeypatch):
    seen = {}

    def fake_find(key):
        seen["key"] = key
        return {"pattern_label": "X"}

    monkeypatch.setattr(patterns, "find_matching_pattern", fake_find)
    result = match_for("Run tests", 1)
    assert result == {"pattern_label": "X"}
    assert seen["key"] == "run tests|1"
