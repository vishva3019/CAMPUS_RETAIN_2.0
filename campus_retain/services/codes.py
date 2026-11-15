"""One-time email codes: stored hashed server-side, short-lived, attempt-limited."""
import secrets
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import EmailCode, utcnow
from .messaging import send_email

SUBJECTS = {
    "signup": "Verify your email",
    "verify": "Verify your email",
    "reset": "Password reset code",
}


def issue_code(email, purpose, college=None):
    """Create and email a new code. Returns False when throttled (a code was sent recently)."""
    cfg = current_app.config
    latest = (EmailCode.query.filter_by(email=email, purpose=purpose)
              .order_by(EmailCode.created_at.desc()).first())
    if latest and utcnow() - latest.created_at < timedelta(seconds=cfg["CODE_RESEND_SECONDS"]):
        return False

    EmailCode.query.filter_by(email=email, purpose=purpose).delete()
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.session.add(EmailCode(
        email=email, purpose=purpose, code_hash=generate_password_hash(code),
        expires_at=utcnow() + timedelta(minutes=cfg["CODE_TTL_MINUTES"]),
    ))
    db.session.commit()

    name = college.display_name if college else "Campus Retain"
    action = ("reset your password" if purpose == "reset"
              else "verify your email and finish setting up your account")
    send_email(
        email,
        f"{name} – {SUBJECTS[purpose]}",
        f"Hello,\n\nUse this code to {action} on Campus Retain ({name}):\n\n"
        f"    {code}\n\nIt expires in {cfg['CODE_TTL_MINUTES']} minutes. "
        "If you did not request it, you can ignore this email.",
        college=college,
    )
    return True


class CodeError(Exception):
    def __init__(self, message, restart=False):
        super().__init__(message)
        self.restart = restart  # the user must request a new code


def consume_code(email, purpose, code):
    """Validate and consume a code, or raise CodeError."""
    cfg = current_app.config
    record = (EmailCode.query.filter_by(email=email, purpose=purpose)
              .order_by(EmailCode.created_at.desc()).with_for_update().first())
    if record is None:
        raise CodeError("No active code. Please request a new one.", restart=True)
    if utcnow() > record.expires_at:
        db.session.delete(record)
        db.session.commit()
        raise CodeError("That code has expired. Please request a new one.", restart=True)
    if record.attempts >= cfg["CODE_MAX_ATTEMPTS"]:
        db.session.delete(record)
        db.session.commit()
        raise CodeError("Too many wrong attempts. Please request a new code.", restart=True)
    if not (code or "").isdigit() or not check_password_hash(record.code_hash, code):
        record.attempts += 1
        db.session.commit()
        raise CodeError("That code is not correct. Please check and try again.")
    db.session.delete(record)
    db.session.commit()
