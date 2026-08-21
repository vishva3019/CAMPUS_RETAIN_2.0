"""Student authentication: sign-up with email verification, login, recovery.

The single most important change from the previous version is that **login no
longer creates accounts**. Previously, posting an unrecognised address to
``/login`` registered it with whatever password was typed and logged the visitor
straight in. Anyone who knew the email format could therefore take ownership of
any colleague's or staff member's address and receive that person's claim
notifications.

Registration is now a distinct flow that requires proving control of the inbox.
"""

from __future__ import annotations

from datetime import timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.extensions import db
from app.models import TokenPurpose, User, VerificationToken, utcnow
from app.security import (
    SESSION_PENDING_PURPOSE,
    SESSION_PENDING_USER_ID,
    describe_password_policy,
    email_domain_allowed,
    normalise_email,
    password_problem,
    safe_redirect_target,
    start_user_session,
)
from app.services import notifications

bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain_hint() -> str:
    return "@" + current_app.config["ALLOWED_EMAIL_DOMAIN"]


def _resend_blocked_for(user: User, purpose: str) -> int:
    """Seconds remaining before another code may be sent, else ``0``.

    Stops the endpoint being used to flood a student's inbox or exhaust the
    daily SMTP quota.
    """
    cooldown = current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    if cooldown <= 0:
        return 0

    latest = VerificationToken.latest_for(user, purpose)
    if latest is None:
        return 0

    ready_at = latest.created_at + timedelta(seconds=cooldown)
    remaining = (ready_at - utcnow()).total_seconds()
    return max(0, int(remaining))


def _issue_and_send(user: User, purpose: str) -> None:
    """Create a fresh code and email it."""
    _token, code = VerificationToken.issue(
        user, purpose, current_app.config["OTP_TTL_MINUTES"]
    )
    db.session.commit()

    if purpose == TokenPurpose.VERIFY_EMAIL:
        notifications.send_verification_code(user, code)
    else:
        notifications.send_password_reset_code(user, code)


def _begin_pending_flow(user: User, purpose: str) -> None:
    """Remember which account is mid-verification.

    Only the row id and the purpose are placed in the session. The code itself
    is stored hashed in the database, because Flask's session cookie is signed
    but *not* encrypted and can be read by whoever holds it.
    """
    session[SESSION_PENDING_USER_ID] = user.id
    session[SESSION_PENDING_PURPOSE] = purpose


def _pending_user(purpose: str) -> User | None:
    if session.get(SESSION_PENDING_PURPOSE) != purpose:
        return None
    user_id = session.get(SESSION_PENDING_USER_ID)
    if not user_id:
        return None
    return db.session.get(User, user_id)


def _clear_pending_flow() -> None:
    session.pop(SESSION_PENDING_USER_ID, None)
    session.pop(SESSION_PENDING_PURPOSE, None)


# ---------------------------------------------------------------------------
# Sign up
# ---------------------------------------------------------------------------

@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template(
            "auth/signup.html",
            domain_hint=_domain_hint(),
            password_policy=describe_password_policy(),
        )

    email = normalise_email(request.form.get("email"))
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not email_domain_allowed(email):
        flash(
            f"Sign-up is limited to {_domain_hint()} addresses.",
            "error",
        )
        return _signup_form(email)

    problem = password_problem(password)
    if problem:
        flash(problem, "error")
        return _signup_form(email)

    if password != confirm:
        flash("The two passwords do not match.", "error")
        return _signup_form(email)

    existing = User.query.filter_by(email=email).first()

    if existing and existing.is_verified:
        # Enumeration is not a meaningful risk here: registration is already
        # restricted to one known university domain, so an attacker learns
        # nothing they could not guess. Being clear is worth more than being
        # coy, since the alternative leaves a locked-out student with no idea
        # what to do next.
        flash("That address already has an account. Please log in instead.", "info")
        return redirect(url_for("auth.login", email=email))

    if existing:
        # An abandoned, unverified sign-up. Let the new attempt take it over,
        # which also means a mistyped address can be corrected by trying again.
        existing.set_password(password)
        user = existing
    else:
        user = User(email=email, is_verified=False)
        user.set_password(password)
        db.session.add(user)

    db.session.flush()  # assign user.id before issuing a token against it

    blocked = _resend_blocked_for(user, TokenPurpose.VERIFY_EMAIL)
    if blocked:
        db.session.commit()
        _begin_pending_flow(user, TokenPurpose.VERIFY_EMAIL)
        flash(
            f"A code was just sent. Please wait {blocked} seconds before "
            "requesting another.",
            "info",
        )
        return redirect(url_for("auth.verify_email"))

    _issue_and_send(user, TokenPurpose.VERIFY_EMAIL)
    _begin_pending_flow(user, TokenPurpose.VERIFY_EMAIL)

    flash(f"We sent a 6-digit code to {email}.", "success")
    return redirect(url_for("auth.verify_email"))


def _signup_form(email: str):
    return (
        render_template(
            "auth/signup.html",
            email=email,
            domain_hint=_domain_hint(),
            password_policy=describe_password_policy(),
        ),
        400,
    )


@bp.route("/verify", methods=["GET", "POST"])
def verify_email():
    user = _pending_user(TokenPurpose.VERIFY_EMAIL)
    if user is None:
        flash("Start by creating an account.", "info")
        return redirect(url_for("auth.signup"))

    if request.method == "GET":
        return render_template("auth/verify.html", email=user.email)

    token = VerificationToken.latest_for(user, TokenPurpose.VERIFY_EMAIL)
    if token is None:
        flash("That code is no longer valid. Request a new one.", "error")
        return redirect(url_for("auth.verify_email"))

    ok, error = token.verify(
        request.form.get("code", ""), current_app.config["OTP_MAX_ATTEMPTS"]
    )
    db.session.commit()

    if not ok:
        flash(error or "Incorrect code.", "error")
        return render_template("auth/verify.html", email=user.email), 400

    user.is_verified = True
    user.register_successful_login()
    db.session.commit()

    _clear_pending_flow()
    start_user_session(user)
    flash("Your account is verified. Welcome to CampusRetain.", "success")
    return redirect(url_for("items.index"))


@bp.route("/verify/resend", methods=["POST"])
def resend_verification():
    user = _pending_user(TokenPurpose.VERIFY_EMAIL)
    if user is None:
        return redirect(url_for("auth.signup"))

    blocked = _resend_blocked_for(user, TokenPurpose.VERIFY_EMAIL)
    if blocked:
        flash(f"Please wait {blocked} seconds before requesting another code.", "info")
    else:
        _issue_and_send(user, TokenPurpose.VERIFY_EMAIL)
        flash("A new code is on its way.", "success")

    return redirect(url_for("auth.verify_email"))


# ---------------------------------------------------------------------------
# Log in / out
# ---------------------------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template(
            "auth/login.html",
            email=request.args.get("email", ""),
            domain_hint=_domain_hint(),
            next=request.args.get("next", ""),
        )

    email = normalise_email(request.form.get("email"))
    password = request.form.get("password") or ""
    next_target = request.form.get("next") or ""

    user = User.query.filter_by(email=email).first()

    # A single generic message for every failure mode, so the form cannot be
    # used to discover which addresses are registered.
    generic = "Incorrect email or password."

    if user is None:
        flash(generic, "error")
        return _login_form(email, next_target)

    if user.is_locked:
        minutes = max(1, user.lockout_remaining_seconds() // 60)
        flash(
            f"Too many failed attempts. Try again in about {minutes} minute(s), "
            "or reset your password.",
            "error",
        )
        return _login_form(email, next_target)

    if not user.check_password(password):
        user.register_failed_login(
            current_app.config["MAX_FAILED_LOGINS"],
            current_app.config["LOGIN_LOCKOUT_MINUTES"],
        )
        db.session.commit()
        flash(generic, "error")
        return _login_form(email, next_target)

    if not user.is_verified:
        # Correct credentials but the inbox was never confirmed. Move them into
        # the verification flow rather than rejecting them outright.
        _begin_pending_flow(user, TokenPurpose.VERIFY_EMAIL)
        if not _resend_blocked_for(user, TokenPurpose.VERIFY_EMAIL):
            _issue_and_send(user, TokenPurpose.VERIFY_EMAIL)
        flash("Please confirm your email address to finish signing up.", "info")
        return redirect(url_for("auth.verify_email"))

    user.register_successful_login()
    db.session.commit()

    start_user_session(user)
    return redirect(safe_redirect_target(next_target, "items.index"))


def _login_form(email: str, next_target: str = ""):
    return (
        render_template(
            "auth/login.html",
            email=email,
            domain_hint=_domain_hint(),
            next=next_target,
        ),
        401,
    )


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Password recovery
# ---------------------------------------------------------------------------

@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html", domain_hint=_domain_hint())

    email = normalise_email(request.form.get("email"))
    user = User.query.filter_by(email=email).first()

    if user is not None and user.is_verified:
        blocked = _resend_blocked_for(user, TokenPurpose.RESET_PASSWORD)
        if not blocked:
            _issue_and_send(user, TokenPurpose.RESET_PASSWORD)
        _begin_pending_flow(user, TokenPurpose.RESET_PASSWORD)

    # Identical response whether or not the address exists. The old endpoint
    # replied "This email address is not registered", handing an attacker a
    # free membership oracle.
    flash(
        "If that address has an account, a 6-digit code is on its way.",
        "info",
    )
    return redirect(url_for("auth.reset_password"))


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        user = _pending_user(TokenPurpose.RESET_PASSWORD)
        return render_template(
            "auth/reset_password.html",
            email=user.email if user else "",
            password_policy=describe_password_policy(),
        )

    user = _pending_user(TokenPurpose.RESET_PASSWORD)
    code = request.form.get("code", "")
    new_password = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    invalid = "That code is incorrect or has expired. Request a new one."

    if user is None:
        flash(invalid, "error")
        return redirect(url_for("auth.forgot_password"))

    problem = password_problem(new_password)
    if problem:
        flash(problem, "error")
        return _reset_form(user.email)

    if new_password != confirm:
        flash("The two passwords do not match.", "error")
        return _reset_form(user.email)

    token = VerificationToken.latest_for(user, TokenPurpose.RESET_PASSWORD)
    if token is None:
        flash(invalid, "error")
        return redirect(url_for("auth.forgot_password"))

    ok, error = token.verify(code, current_app.config["OTP_MAX_ATTEMPTS"])
    db.session.commit()

    if not ok:
        flash(error or invalid, "error")
        return _reset_form(user.email)

    user.set_password(new_password)
    # A successful reset is also proof of inbox control, and clears any lockout
    # so a locked-out student has a way back in.
    user.is_verified = True
    user.locked_until = None
    user.failed_logins = 0
    db.session.commit()

    _clear_pending_flow()
    flash("Your password has been changed. Please log in.", "success")
    return redirect(url_for("auth.login", email=user.email))


def _reset_form(email: str):
    return (
        render_template(
            "auth/reset_password.html",
            email=email,
            password_policy=describe_password_policy(),
        ),
        400,
    )
