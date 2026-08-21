"""Outbound email over SMTP.

Two deliberate design points:

**One connection, many messages.** The previous implementation opened a fresh
TCP connection, STARTTLS handshake and SMTP login for *every* message. Approving
a claim sends notices to both the student and the admin, so a single request paid
that cost twice. On a serverless platform with a short execution budget that is
the difference between a request completing and timing out. :func:`send_messages`
reuses one authenticated connection.

**Failure is never fatal.** A student's claim must still be recorded if the mail
server is unreachable. Every function here returns a count or a boolean and logs
the problem; none of them raise into a request handler.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Sequence

from flask import current_app


@dataclass(frozen=True)
class OutboundEmail:
    to: str
    subject: str
    body: str


def is_configured() -> bool:
    cfg = current_app.config
    return bool(cfg.get("MAIL_USERNAME") and cfg.get("MAIL_PASSWORD"))


def _build(message: OutboundEmail) -> EmailMessage:
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = message.subject
    # An explicit display name measurably improves deliverability through
    # university mail gateways, which tend to distrust bare addresses.
    msg["From"] = formataddr((cfg["MAIL_FROM_NAME"], cfg["MAIL_USERNAME"]))
    msg["To"] = message.to
    msg.set_content(message.body)
    return msg


def send_messages(messages: Sequence[OutboundEmail]) -> int:
    """Send a batch over a single connection. Returns the number delivered."""
    messages = [m for m in messages if m.to]
    if not messages:
        return 0

    if not is_configured():
        current_app.logger.warning(
            "Email not configured (MAIL_USERNAME/MAIL_PASSWORD unset); "
            "skipping %d message(s)",
            len(messages),
        )
        return 0

    cfg = current_app.config
    sent = 0
    try:
        with smtplib.SMTP(
            cfg["MAIL_SERVER"],
            cfg["MAIL_PORT"],
            timeout=cfg["MAIL_TIMEOUT_SECONDS"],
        ) as server:
            server.starttls()
            server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            for message in messages:
                try:
                    server.send_message(_build(message))
                    sent += 1
                except smtplib.SMTPException:
                    # Log the failing recipient but keep going; one bad address
                    # should not sink the rest of the batch.
                    current_app.logger.exception(
                        "Failed to send %r", message.subject
                    )
    except (smtplib.SMTPException, OSError):
        current_app.logger.exception("SMTP connection failed")
        return sent

    current_app.logger.info("Sent %d/%d email(s)", sent, len(messages))
    return sent


def send_email(to: str, subject: str, body: str) -> bool:
    """Convenience wrapper for a single message."""
    return send_messages([OutboundEmail(to=to, subject=subject, body=body)]) == 1
