from app.decision import classify_remediation


def test_test_failure_escalates():
    action, _ = classify_remediation("Run tests", "AssertionError in test_add", "FAILED", 1, None)
    assert action == "HUMAN_ESCALATION"


def test_deploy_health_regression_rolls_back():
    action, _ = classify_remediation(
        "Deploy", "health check failed; container did not become healthy", "503", 1, None
    )
    assert action == "AUTO_ROLLBACK"


def test_transient_restarts():
    action, _ = classify_remediation("Pull image", "connection timed out", "i/o timeout", 1, None)
    assert action == "SERVICE_RESTART"


def test_falls_back_to_llm_severity():
    action, reason = classify_remediation("Mystery", "totally unclear", None, 1, "AUTO_ROLLBACK")
    assert action == "AUTO_ROLLBACK"
    assert "model" in reason


def test_default_is_human_escalation():
    action, _ = classify_remediation("Mystery", "totally unclear", None, 1, None)
    assert action == "HUMAN_ESCALATION"
