"""Authentication, authorisation and input-validation helpers."""

from __future__ import annotations

import secrets
from functools import wraps
from typing import Callable
from urllib.parse import urlparse

from flask import (
    current_app,
    flash,
    redirect,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from app.models import User

# Session keys, named in one place so nothing depends on a bare string.
SESSION_USER_EMAIL = "user_email"
SESSION_IS_ADMIN = "is_admin"

# Keys used to carry a partially-completed OTP flow between requests. Only
# opaque identifiers are stored here -- never the code itself, which lives
# hashed in the database (see VerificationToken).
SESSION_PENDING_USER_ID = "pending_user_id"
SESSION_PENDING_PURPOSE = "pending_purpose"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def start_user_session(user: User) -> None:
    """Log a user in, discarding any pre-existing session state.

    Clearing first mitigates session fixation: a value planted in the session
    before authentication (for example a half-finished reset flow) cannot
    survive into the authenticated session.
    """
    session.clear()
    session[SESSION_USER_EMAIL] = user.email
    session.permanent = True


def start_admin_session(email: str) -> None:
    session.clear()
    session[SESSION_IS_ADMIN] = True
    session[SESSION_USER_EMAIL] = email
    session.permanent = True


def current_user_email() -> str | None:
    return session.get(SESSION_USER_EMAIL)


def current_user() -> User | None:
    email = current_user_email()
    if not email:
        return None
    return User.query.filter_by(email=email).first()


def is_admin() -> bool:
    return session.get(SESSION_IS_ADMIN) is True


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(view: Callable) -> Callable:
    """Require an authenticated student (or an admin, who outranks one)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user_email():
            if _wants_json():
                return {"error": "Authentication required."}, 401
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view: Callable) -> Callable:
    """Require an authenticated administrator."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            if _wants_json():
                return {"error": "Administrator access required."}, 403
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapper


def _wants_json() -> bool:
    """True when the caller is an API client rather than a browser navigation."""
    if request.path.startswith("/api/"):
        return True
    return request.accept_mimetypes.best == "application/json"


# ---------------------------------------------------------------------------
# Administrator credentials
# ---------------------------------------------------------------------------

def verify_admin_credentials(email: str, password: str) -> bool:
    """Check administrator credentials in constant time where it matters.

    The previous implementation compared both the email and a *plaintext*
    password from the environment with ``==``. The password is now stored as a
    hash, so a leaked environment listing no longer discloses it.
    """
    cfg = current_app.config
    expected_email = (cfg.get("ADMIN_EMAIL") or "").strip().lower()
    expected_hash = cfg.get("ADMIN_PASSWORD_HASH") or ""

    if not expected_email or not expected_hash:
        current_app.logger.error(
            "Admin login attempted but ADMIN_EMAIL/ADMIN_PASSWORD_HASH are "
            "not configured."
        )
        return False

    email_ok = secrets.compare_digest(
        (email or "").strip().lower(), expected_email
    )

    # Always run the hash comparison, even when the email did not match, so the
    # response time does not reveal whether the address was correct.
    try:
        password_ok = check_password_hash(expected_hash, password or "")
    except (ValueError, TypeError):
        current_app.logger.error("ADMIN_PASSWORD_HASH is not a valid hash.")
        return False

    return email_ok and password_ok


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def normalise_email(raw: str | None) -> str:
    return (raw or "").strip().lower()


def email_domain_allowed(email: str) -> bool:
    """True when the address sits on the configured organisation domain.

    Parses the domain rather than using ``endswith``, so neither
    ``someone@evil-ced.alliance.edu.in`` nor an address containing two ``@``
    signs can slip through.
    """
    allowed = current_app.config["ALLOWED_EMAIL_DOMAIN"]
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local:
        return False
    return domain == allowed


def describe_password_policy() -> str:
    return (
        f"Use at least {current_app.config['MIN_PASSWORD_LENGTH']} characters, "
        "including a letter and a number."
    )


def password_problem(password: str) -> str | None:
    """Return a human-readable reason the password is unacceptable, or ``None``.

    The old signup path accepted an empty string, hashing ``""`` into a
    perfectly valid credential.
    """
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    if not password:
        return "Please choose a password."
    if len(password) < minimum:
        return f"Password must be at least {minimum} characters long."
    if len(password) > 200:
        return "Password must be shorter than 200 characters."
    if not any(char.isalpha() for char in password):
        return "Password must contain at least one letter."
    if not any(char.isdigit() for char in password):
        return "Password must contain at least one number."
    return None


def safe_redirect_target(candidate: str | None, fallback_endpoint: str) -> str:
    """Sanitise a ``?next=`` parameter into a same-origin relative path.

    Without this an attacker could send ``/login?next=https://evil.example`` and
    use the site's own login page as a springboard for a phishing redirect.
    """
    fallback = url_for(fallback_endpoint)
    if not candidate:
        return fallback

    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not parsed.path.startswith("/"):
        return fallback
    if parsed.path.startswith("//"):
        return fallback

    target = parsed.path
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return target


def flash_errors(*messages: str | None) -> None:
    for message in messages:
        if message:
            flash(message, "error")
