"""Gmail SMTP delivery for incident reports (TLS on port 587).

The app password is read from settings and used only for the SMTP login; it is
never logged.
"""

from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings


def build_message(subject: str, html_body: str, text_body: str) -> MIMEMultipart:
    """Construct the multipart (text + HTML) email message. No network I/O."""
    settings = get_settings()
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.gmail_from
    message["To"] = settings.gmail_to
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message


def send_email(subject: str, html_body: str, text_body: str) -> None:
    """Send a multipart (text + HTML) email. Raises on failure."""
    settings = get_settings()
    if not settings.gmail_app_password:
        raise RuntimeError("GMAIL_APP_PASSWORD is not configured")

    message = build_message(subject, html_body, text_body)
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls(context=context)
        server.login(settings.gmail_from, settings.gmail_app_password)
        server.sendmail(settings.gmail_from, [settings.gmail_to], message.as_string())
