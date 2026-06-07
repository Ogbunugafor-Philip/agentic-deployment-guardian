from app.log_parser import clean_log, parse_logs

RAW = "\r\n".join([
    "2026-06-07T14:29:03.1Z \x1b[32m##[group]Run tests\x1b[0m",
    "2026-06-07T14:29:03.2Z Running suite...",
    "2026-06-07T14:29:03.3Z ",
    "2026-06-07T14:29:03.3Z ",
    "2026-06-07T14:29:03.4Z tests/test_widget.py::test_add FAILED",
    "2026-06-07T14:29:03.5Z ERROR: AssertionError: expected 4 got 5",
    "2026-06-07T14:29:03.6Z ##[endgroup]",
    "2026-06-07T14:29:03.7Z ##[error]Process completed with exit code 1.",
])


def test_strips_timestamps_and_ansi_and_blanks():
    lines = clean_log(RAW)
    assert not any(line.startswith("2026-") for line in lines)
    assert not any("\x1b" in line for line in lines)
    # repeated blank lines collapsed
    assert "\n\n\n" not in "\n".join(lines)


def test_extracts_failed_step_and_exit_code():
    result = parse_logs(RAW)
    assert result["failed_step"] == "Run tests"
    assert result["exit_code"] == 1


def test_extracts_relevant_error_lines():
    result = parse_logs(RAW)
    joined = "\n".join(result["error_lines"])
    assert "AssertionError" in joined
    assert "FAILED" in joined


def test_handles_empty_log():
    result = parse_logs("")
    assert result["failed_step"] is None
    assert result["exit_code"] is None
    assert "no explicit error" in result["summary"].lower()
