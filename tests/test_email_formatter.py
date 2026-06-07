import app.email_sender as email_sender
from app.email_sender import build_message


def test_build_message_structure():
    msg = build_message("[Guardian] Incident #1 — Run tests — RECOVERED", "<p>hi</p>", "hi")
    assert msg["Subject"] == "[Guardian] Incident #1 — Run tests — RECOVERED"
    assert msg["From"] == "philiposita1041@gmail.com"
    assert msg["To"] == "philiposita1041@gmail.com"
    assert msg.is_multipart()
    types = {part.get_content_type() for part in msg.get_payload()}
    assert types == {"text/plain", "text/html"}


def test_build_message_no_network():
    # build_message must not require the app password (only send_email does).
    msg = build_message("s", "<b>b</b>", "b")
    assert msg.get_content_subtype() == "alternative"


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.actions = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.actions.append("starttls")

    def login(self, user, password):
        self.actions.append(("login", user))  # never record the password

    def sendmail(self, frm, to, msg):
        self.actions.append(("sendmail", frm, tuple(to)))


def test_send_email_uses_tls_and_login(monkeypatch):
    monkeypatch.setattr(email_sender.smtplib, "SMTP", _FakeSMTP)
    email_sender.send_email("subj", "<p>h</p>", "h")
    smtp = _FakeSMTP.instances[-1]
    assert smtp.host == "smtp.gmail.com" and smtp.port == 587
    assert "starttls" in smtp.actions
    assert ("login", "philiposita1041@gmail.com") in smtp.actions
    assert any(a[0] == "sendmail" for a in smtp.actions if isinstance(a, tuple))
