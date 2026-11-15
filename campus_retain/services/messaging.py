"""Email and SMS delivery. Failures are logged, never raised into request handlers."""
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from flask import current_app

try:
    from twilio.rest import Client as TwilioClient
except ImportError:  # optional dependency
    TwilioClient = None


def outbox():
    """In-memory outbox used by MAIL_BACKEND=memory (tests)."""
    return current_app.extensions.setdefault("mail_outbox", [])


def send_email(to, subject, body, college=None):
    cfg = current_app.config
    from_name = (college.mail_from_name or college.display_name) if college else cfg["MAIL_DEFAULT_FROM_NAME"]
    backend = cfg["MAIL_BACKEND"]

    if backend == "memory":
        outbox().append({"to": to, "subject": subject, "body": body, "from_name": from_name})
        return True
    if backend == "console":
        current_app.logger.info("EMAIL to=%s subject=%s\n%s", to, subject, body)
        return True

    if not cfg.get("MAIL_USERNAME") or not cfg.get("MAIL_PASSWORD"):
        current_app.logger.warning("Email not sent (MAIL_USERNAME/MAIL_PASSWORD missing): %s", subject)
        return False
    try:
        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, cfg["MAIL_USERNAME"]))
        msg["To"] = to
        if college and college.contact_email:
            msg["Reply-To"] = college.contact_email
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as server:
            server.starttls()
            server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
        return True
    except Exception:
        current_app.logger.exception("Email delivery failed: %s", subject)
        return False


def normalize_phone(raw):
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.strip().startswith("+"):
        return "+" + digits if 8 <= len(digits) <= 15 else None
    if len(digits) == 10:
        return current_app.config["SMS_DEFAULT_COUNTRY_CODE"] + digits
    return None


def send_sms(to, body):
    cfg = current_app.config
    number = normalize_phone(to)
    if not number:
        return False
    if not (cfg.get("TWILIO_ACCOUNT_SID") and cfg.get("TWILIO_AUTH_TOKEN")
            and cfg.get("TWILIO_PHONE_NUMBER") and TwilioClient):
        return False
    try:
        TwilioClient(cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"]).messages.create(
            body=body, from_=cfg["TWILIO_PHONE_NUMBER"], to=number)
        return True
    except Exception:
        current_app.logger.exception("SMS delivery failed")
        return False
