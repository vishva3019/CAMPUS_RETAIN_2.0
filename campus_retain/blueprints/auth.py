"""Registration, login, email verification and password reset.

The college is decided by the email domain on the server. A branded login page
(/c/<slug>/login) additionally refuses emails from other colleges.
"""
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from flask import (Blueprint, current_app, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import Campus, College, CollegeStatus, User, utcnow
from ..security import (STUDENT, college_for_email, get_role, login_user,
                        logout_user)
from ..services.audit import audit
from ..services.codes import CodeError, consume_code, issue_code

bp = Blueprint("auth", __name__)


def _cfg(key):
    return current_app.config[key]


def _limit(key):
    return lambda: current_app.config[key]


def _home_for(user):
    from flask import current_app

    from .spa import spa_available

    staff = any(user.has_permission(p) for p in ("claims.review", "items.manage", "collection.verify"))
    platform = bool(user.role and user.role.is_platform)
    if current_app.config.get("USE_REACT_APP") and spa_available():
        return url_for("spa.app_shell", path="platform" if platform else "admin" if staff else "")
    if platform:
        return url_for("platform.home")
    if staff:
        return url_for("admin.dashboard")
    return url_for("student.dashboard")


def _safe_next(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def _branded_college(slug):
    if not slug:
        return None
    college = College.query.filter_by(slug=slug).first()
    if college is None or college.status != CollegeStatus.ACTIVE:
        return None
    return college


def _login_page(template="login.html", college=None, status=200, **ctx):
    return render_template(template, college=college, **ctx), status


def _code_page(purpose, email, college=None, message=None, error=None, status=200):
    campuses = []
    if purpose == "signup" and college is not None:
        campuses = [c for c in college.campuses if c.is_active]
    return render_template(
        "reset_password.html", purpose=purpose, email=email, college=college,
        campuses=campuses, message=message, error=error,
        min_password_length=_cfg("MIN_PASSWORD_LENGTH"),
    ), status


def _start_pending(email, purpose, college=None):
    session["pending_email"] = email
    session["pending_purpose"] = purpose
    session["pending_college_id"] = college.id if college else None


def _clear_pending():
    for key in ("pending_email", "pending_purpose", "pending_college_id"):
        session.pop(key, None)


# ---------------------------------------------------------------- login / register

def check_password(user, password):
    """Password check with lockout, shared by the classic and React sign-in.
    Returns None on success, or (message, status). Commits failed attempts."""
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        return (f"Too many failed attempts. Try again in {minutes} minutes or reset your password.", 429)
    try:
        valid = check_password_hash(user.password, password)
    except (ValueError, TypeError):
        valid = False  # legacy or corrupt value: never compare plain text
    if not valid or not user.is_active:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= _cfg("MAX_FAILED_LOGINS"):
            user.locked_until = now + timedelta(minutes=_cfg("LOCKOUT_MINUTES"))
            user.failed_login_count = 0
            audit("auth.locked", user, actor=user)
        audit("auth.login_failed", user, actor=user)
        db.session.commit()
        return ("Incorrect email or password. Use 'Forgot password?' to reset it.", 401)
    if user.college_id is not None and (user.college is None or not user.college.is_active):
        return ("Your college's Campus Retain account is not active.", 403)
    user.failed_login_count = 0
    user.locked_until = None
    return None


def react_signin_url(**args):
    """The React sign-in page, when it is built and switched on."""
    from .spa import spa_available
    if current_app.config.get("USE_REACT_APP") and spa_available():
        return url_for("spa.app_shell", path="signin", **{k: v for k, v in args.items() if v})
    return None


@bp.route("/login", methods=["GET", "POST"])
@bp.route("/c/<slug>/login", methods=["GET", "POST"])
@bp.route("/admin_login", methods=["GET", "POST"], endpoint="admin_login")
@limiter.limit(_limit("LOGIN_RATE_LIMIT"), methods=["POST"])
def login(slug=None):
    template = "admin_login.html" if request.endpoint == "auth.admin_login" else "login.html"
    college = _branded_college(slug)
    if slug and college is None:
        return render_template("error.html", code=404,
                               message="This college is not available on Campus Retain."), 404

    if g.get("user"):
        return redirect(_home_for(g.user))

    if request.method == "GET":
        if request.endpoint != "auth.admin_login":
            target = react_signin_url(college=college.slug if college else None,
                                      next=_safe_next(request.args.get("next")))
            if target:
                return redirect(target)
        return _login_page(template, college)

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email or "@" not in email or len(email) > 120:
        return _login_page(template, college, 400, error="Enter a valid email address.")

    user = User.query.filter_by(email=email).first()

    if user is None:
        target = college_for_email(email)
        if target is None:
            return _login_page(template, college, 400,
                               error="Your college email domain isn't registered on Campus Retain yet.")
        if college is not None and target.id != college.id:
            return _login_page(template, college, 400,
                               error=f"Use your {college.display_name} email address on this page.")
        issue_code(email, "signup", target)
        _start_pending(email, "signup", target)
        return _code_page("signup", email, target,
                          message="New here? We sent a 6-digit verification code to")

    # Existing account
    if college is not None and user.college_id != college.id:
        return _login_page(template, college, 400, error="Incorrect email or password.")

    error = check_password(user, password)
    if error:
        return _login_page(template, college, error[1], error=error[0])
    now = utcnow()

    if not user.is_verified:
        # 2.0 accounts were never email-verified: prove ownership once.
        db.session.commit()
        issue_code(email, "verify", user.college)
        _start_pending(email, "verify", user.college)
        return _code_page("verify", email, user.college,
                          message="Please confirm your email once. We sent a 6-digit code to")

    user.last_login_at = now
    audit("auth.login", user, actor=user)
    db.session.commit()
    login_user(user)
    return redirect(_safe_next(request.args.get("next")) or _home_for(user))


# ---------------------------------------------------------------- password reset

@bp.route("/forgot-password", methods=["POST"])
@limiter.limit(_limit("CODE_REQUEST_RATE_LIMIT"))
def forgot_password():
    email = request.form.get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first() if email else None
    if user is not None and user.is_active:
        issue_code(email, "reset", user.college)
        audit("auth.reset_requested", user, actor=user)
        db.session.commit()
    # Same response either way, so the form can't be used to discover accounts.
    _start_pending(email, "reset", user.college if user else None)
    return _code_page("reset", email, user.college if user else None,
                      message="If an account exists, we sent a 6-digit code to")


@bp.route("/resend-code", methods=["POST"])
@limiter.limit(_limit("CODE_REQUEST_RATE_LIMIT"))
def resend_code():
    email, purpose = session.get("pending_email"), session.get("pending_purpose")
    if not email or purpose not in ("signup", "reset", "verify"):
        return _login_page(error="Your verification session expired. Please start again.", status=400)
    college = db.session.get(College, session.get("pending_college_id")) if session.get("pending_college_id") else None
    exists = User.query.filter_by(email=email).first() is not None
    if purpose == "signup" or exists:
        sent = issue_code(email, purpose, college)
    else:
        sent = True
    msg = "We sent a new code to" if sent else "Please wait a minute before asking for another code. Check"
    return _code_page(purpose, email, college, message=msg)


# ---------------------------------------------------------------- verify code

@bp.route("/verify-code", methods=["POST"])
@limiter.limit(_limit("CODE_VERIFY_RATE_LIMIT"))
def verify_code():
    email = session.get("pending_email")
    purpose = session.get("pending_purpose")
    if not email or purpose not in ("signup", "reset", "verify"):
        return _login_page(error="Your verification session expired. Please start again.", status=400)

    college = db.session.get(College, session.get("pending_college_id")) if session.get("pending_college_id") else None
    otp = request.form.get("otp", "").strip()
    new_password = request.form.get("new_password", "")

    if purpose in ("signup", "reset") and len(new_password) < _cfg("MIN_PASSWORD_LENGTH"):
        return _code_page(purpose, email, college, status=400,
                          error=f"Password must be at least {_cfg('MIN_PASSWORD_LENGTH')} characters.")

    campus = None
    if purpose == "signup":
        # Re-check on the server: the domain must still map to this active college.
        target = college_for_email(email)
        if target is None or college is None or target.id != college.id:
            _clear_pending()
            return _login_page(error="Your college is not accepting registrations right now.", status=400)
        campus_id = request.form.get("campus_id", type=int)
        if campus_id:
            campus = Campus.query.filter_by(id=campus_id, college_id=college.id, is_active=True).first()
            if campus is None:
                return _code_page(purpose, email, college, status=400, error="Choose a valid campus.")

    try:
        consume_code(email, purpose, otp)
    except CodeError as exc:
        if exc.restart:
            _clear_pending()
            return _login_page(error=str(exc), status=400)
        return _code_page(purpose, email, college, error=str(exc), status=400)

    user = User.query.filter_by(email=email).first()
    now = utcnow()

    if purpose == "signup":
        if user is None:
            user = User(email=email, college_id=college.id, campus_id=campus.id if campus else None,
                        role_id=get_role(STUDENT).id, password=generate_password_hash(new_password),
                        email_verified_at=now, created_at=now)
            db.session.add(user)
            db.session.flush()
            audit("auth.registered", user, actor=user)
        else:
            # Someone registered in between; treat as a verified password set.
            user.password = generate_password_hash(new_password)
            user.email_verified_at = user.email_verified_at or now
            user.session_version += 1
    elif user is None:
        _clear_pending()
        return _login_page(error="Your verification session expired. Please start again.", status=400)
    elif purpose == "reset":
        user.password = generate_password_hash(new_password)
        user.session_version += 1           # sign out every other session
        user.failed_login_count, user.locked_until = 0, None
        user.email_verified_at = user.email_verified_at or now
        audit("auth.password_reset", user, actor=user)
    else:  # verify
        user.email_verified_at = now
        audit("auth.email_verified", user, actor=user)

    _clear_pending()
    if purpose == "reset":
        db.session.commit()
        return _login_page(success="Password updated. You can sign in now.")

    user.last_login_at = now
    db.session.commit()
    if user.college_id is not None and not user.college.is_active:
        return _login_page(error="Your college's Campus Retain account is not active.", status=403)
    login_user(user)
    return redirect(_home_for(user))


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    return redirect(url_for("student.index"))


def random_unusable_password():
    """Hash of a random secret nobody knows: the account must use password reset first."""
    return generate_password_hash(secrets.token_urlsafe(32))
