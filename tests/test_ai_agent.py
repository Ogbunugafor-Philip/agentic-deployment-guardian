import app.ai_agent as ai


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeChain:
    def __init__(self, content):
        self._content = content
        self.last_input = None

    def invoke(self, payload):
        self.last_input = payload
        return FakeResponse(self._content)


def test_extract_json_handles_fences():
    assert ai._extract_json('```json\n{"severity":"SERVICE_RESTART"}\n```')["severity"] == "SERVICE_RESTART"
    assert ai._extract_json('noise {"a":1} tail')["a"] == 1
    assert ai._extract_json("no json") == {}


def test_pattern_note():
    note = ai._pattern_note({"pattern_label": "Recurring test failure",
                             "occurrence_count": 3, "suggested_fix": "fix it"})
    assert "Recurring test failure" in note and "3 times" in note and "fix it" in note
    assert ai._pattern_note(None) == ""


def test_analyze_failure_parses(monkeypatch):
    content = ('{"failure_point":"Run tests","explanation":"a test failed",'
               '"suggested_fix":"fix the test","severity":"HUMAN_ESCALATION"}')
    chain = FakeChain(content)
    monkeypatch.setattr(ai, "_build_chain", lambda: chain)
    result = ai.analyze_failure("Run tests", "summary", 1, pattern={"pattern_label": "Recurring test failure", "occurrence_count": 2, "suggested_fix": "x"})
    assert result["severity_hint"] == "HUMAN_ESCALATION"
    assert "Run tests" in result["root_cause"]
    assert "a test failed" in result["root_cause"]
    # the known-pattern context was injected into the prompt
    assert "known pattern" in chain.last_input["pattern_note"].lower()
