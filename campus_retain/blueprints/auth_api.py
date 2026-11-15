"""JSON sign-up and sign-in for the animated onboarding screens (``/api/v1/auth``).

Flow: pick a college -> details -> 6-digit code to the college email -> account created.
The account row only exists after the code is confirmed (PendingRegistration holds the
form until then). Responses never reveal whether an email already has an account: the
owner of that address gets an email instead.
"""
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request, session
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import AuditLog, EmailCode, PendingRegistration, User, utcnow
from ..security import STUDENT, get_role, login_user
from ..services.audit import audit
from ..services.codes import CodeError, consume_code, issue_code
from ..services.messaging import send_email
from ..services.onboarding import (YEARS, OnboardingError, active_college, check_new_password,
                                   clean_department, clean_name, clean_student_id, clean_year,
                                   college_card, college_email, department_suggestions,
                                   signup_colleges)
from .auth import _clear_pending, _home_for, _safe_next, _start_pending, check_password

bp = Blueprint("auth_api", __name__, url_prefix="/api/v1/auth")

# Compared against when an email has no account, so both paths take about as long.
_DUMMY_HASH = generate_password_hash("campus-retain-timing-equaliser")


def _limit(key):
    return lambda: current_app.config[key]


def _err(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


def _data():
    return request.get_json(silent=True) or {}


def _resend_in(email, purpose):
    latest = (EmailCode.query.filter_by(email=email, purpose=purpose)
              .order_by(EmailCode.created_at.desc()).first())
    if latest is None:
        return 0
    wait = current_app.config["CODE_RESEND_SECONDS"] - (utcnow() - latest.created_at).total_seconds()
    return max(0, int(wait + 0.999))


def _code_sent(email, purpose):
    cfg = current_app.config
    # The countdown is shown even when no code was sent (unknown email): same response.
    return jsonify({"status": "code_sent", "email": email, "purpose": purpose,
                    "resend_in": _resend_in(email, purpose) or cfg["CODE_RESEND_SECONDS"],
                    "expires_in": cfg["CODE_TTL_MINUTES"] * 60})


def _signed_in_json(user, **extra):
    college = user.college
    return jsonify({"status": "signed_in", "home": _home_for(user),
                    "user": {"full_name": user.full_name, "email": user.email},
                    "college": {"name": college.name, "display_name": college.display_name} if college else None,
                    **extra})


# ---------------------------------------------------------------- public data

@bp.route("/bootstrap")
def bootstrap():
    cfg = current_app.config
    user = g.get("user")
    resp = jsonify({
        "csrf_token": generate_csrf(),
        "signed_in": user is not None,
        "home": _home_for(user) if user is not None else None,
        "colleges": [college_card(c) for c in signup_colleges()],
        "years": [{"value": k, "label": v} for k, v in YEARS.items()],
        "password_min": cfg["MIN_PASSWORD_LENGTH"],
        "code": {"length": 6, "ttl_minutes": cfg["CODE_TTL_MINUTES"],
                 "resend_seconds": cfg["CODE_RESEND_SECONDS"], "max_attempts": cfg["CODE_MAX_ATTEMPTS"]},
        "remember_days": cfg["REMEMBER_DAYS"],
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/colleges/<int:college_id>/departments")
def departments(college_id):
    try:
        college = active_college(college_id)
    except OnboardingError as exc:
        return _err(str(exc), 404)
    return jsonify({"items": department_suggestions(college)})


# ---------------------------------------------------------------- registration

def _notify_existing_account(user, college):
    """Someone tried to sign up with an email that already has an account. Tell the owner
    (at most every 10 minutes) instead of telling the person filling in the form."""
    recent = (AuditLog.query.filter(AuditLog.action == "auth.signup_existing", AuditLog.target_id == user.id,
                                    AuditLog.created_at > utcnow() - timedelta(minutes=10)).first())
    if recent is None:
        send_email(user.email, f"{college.display_name} – You already have a Campus Retain account",
                   "Hello,\n\nSomeone (probably you) tried to create a new Campus Retain account with this "
                   "email address, but you already have one.\n\nSign in with your password, or use "
                   "'Forgot password?' on the sign-in screen to set a new one.\n\nIf this wasn't you, "
                   "you can ignore this email: nothing has changed.", college=college)
        audit("auth.signup_existing", user, actor=user)
        db.session.commit()


@bp.route("/register", methods=["POST"])
@limiter.limit(_limit("REGISTER_RATE_LIMIT"))
def register():
    if g.get("user") is not None:
        return _err("You're already signed in.", 409, home=_home_for(g.user))
    f = _data()
    try:
        college = active_college(f.get("college_id"))
        full_name = clean_name(f.get("full_name"))
        email = college_email(f.get("email"), college)
        student_id = clean_student_id(f.get("student_id"))
        department_id, department = clean_department(f.get("department"), college)
        year = clean_year(f.get("year_of_study"))
        password = f.get("password")
        if password != f.get("confirm_password"):
            raise OnboardingError("The passwords don't match.", "confirm_password")
        check_new_password(password, email, student_id)
    except OnboardingError as exc:
        return _err(str(exc), exc.status, field=exc.field)

    password_hash = generate_password_hash(password)   # done on every path (timing)
    _start_pending(email, "signup", college)
    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        _notify_existing_account(existing, college)
        return _code_sent(email, "signup")

    now = utcnow()
    PendingRegistration.query.filter(PendingRegistration.expires_at < now).delete()
    pending = PendingRegistration.query.filter_by(email=email).first() or PendingRegistration(email=email)
    pending.college_id, pending.full_name, pending.student_id = college.id, full_name, student_id
    pending.department_id, pending.department_name, pending.year_of_study = department_id, department, year
    pending.password_hash, pending.created_at = password_hash, now
    pending.expires_at = now + timedelta(hours=current_app.config["PENDING_REGISTRATION_HOURS"])
    db.session.add(pending)
    db.session.commit()
    issue_code(email, "signup", college)    # throttled per email; the form details are kept either way
    return _code_sent(email, "signup")


@bp.route("/register/verify", methods=["POST"])
@limiter.limit(_limit("CODE_VERIFY_RATE_LIMIT"))
def register_verify():
    email, purpose = session.get("pending_email"), session.get("pending_purpose")
    if not email or purpose != "signup":
        return _err("Your sign-up session has ended. Please fill in the form again.", 410, restart=True)
    try:
        consume_code(email, "signup", str(_data().get("otp") or "").strip())
    except CodeError as exc:
        return _err(str(exc), 400, expired=exc.restart)

    now = utcnow()
    pending = PendingRegistration.query.filter_by(email=email).first()
    if pending is None or pending.expires_at < now or pending.college_id != session.get("pending_college_id"):
        _clear_pending()
        return _err("Your sign-up has expired. Please fill in the form again.", 410, restart=True)
    college = pending.college
    try:
        college = active_college(college.id, listed=False)
        college_email(email, college)          # the college's domains may have changed since
    except OnboardingError as exc:
        _clear_pending()
        return _err(str(exc), 400, restart=True)

    if User.query.filter_by(email=email).first() is not None:
        db.session.delete(pending)
        db.session.commit()
        _clear_pending()
        return _err("An account with this email already exists. Please sign in.", 409, restart=True)
    if User.query.filter_by(college_id=college.id, student_id=pending.student_id).first() is not None:
        return _err(f"The student ID {pending.student_id} is already registered at {college.name}. "
                    "Sign in instead, or contact your college's lost-and-found office if this isn't you.",
                    409, restart=True)

    user = User(email=email, college_id=college.id, role_id=get_role(STUDENT).id,
                full_name=pending.full_name, student_id=pending.student_id,
                department_id=pending.department_id, department_name=pending.department_name,
                year_of_study=pending.year_of_study, password=pending.password_hash,
                email_verified_at=now, created_at=now, last_login_at=now)
    db.session.add(user)
    db.session.delete(pending)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return _err("This account was just created. Please sign in.", 409, restart=True)
    audit("auth.registered", user, actor=user, via="onboarding")
    db.session.commit()
    _clear_pending()
    login_user(user)
    return _signed_in_json(user)


# ---------------------------------------------------------------- codes

@bp.route("/resend", methods=["POST"])
@limiter.limit(_limit("REGISTER_RATE_LIMIT"))
def resend():
    email, purpose = session.get("pending_email"), session.get("pending_purpose")
    if not email or purpose not in ("signup", "verify", "reset"):
        return _err("Your session has ended. Please start again.", 410, restart=True)
    college_id = session.get("pending_college_id")
    wait = _resend_in(email, purpose)
    if wait:
        return _err(f"Please wait {wait} seconds before asking for another code.", 429, resend_in=wait)
    user = User.query.filter_by(email=email).first()
    if purpose == "signup":
        pending = PendingRegistration.query.filter_by(email=email).first()
        if user is None:
            if pending is None or pending.expires_at < utcnow():
                _clear_pending()
                return _err("Your sign-up has expired. Please fill in the form again.", 410, restart=True)
            issue_code(email, purpose, pending.college)
    elif user is not None and user.is_active and user.college_id == college_id:
        issue_code(email, purpose, user.college)
    return _code_sent(email, purpose)


# ---------------------------------------------------------------- sign in

@bp.route("/login", methods=["POST"])
@limiter.limit(_limit("LOGIN_RATE_LIMIT"))
def login():
    f = _data()
    try:
        college = active_college(f.get("college_id"), listed=False)
        email = college_email(f.get("email"), college)
    except OnboardingError as exc:
        return _err(str(exc), exc.status, field=exc.field)
    password = f.get("password") if isinstance(f.get("password"), str) else ""

    user = User.query.filter_by(email=email).first()
    if user is None or user.college_id != college.id:
        check_password_hash(_DUMMY_HASH, password)
        return _err("Incorrect email or password. Use 'Forgot password?' to reset it.", 401)
    error = check_password(user, password)
    if error:
        return _err(*error)

    remember = bool(f.get("remember"))
    if not user.is_verified:
        db.session.commit()
        issue_code(email, "verify", college)
        _start_pending(email, "verify", college)
        session["pending_remember"] = remember
        return _code_sent(email, "verify")

    user.last_login_at = utcnow()
    audit("auth.login", user, actor=user, via="onboarding")
    db.session.commit()
    login_user(user, remember=remember)
    nxt = _safe_next(f.get("next"))
    return _signed_in_json(user, home=nxt or _home_for(user))


@bp.route("/verify-email", methods=["POST"])
@limiter.limit(_limit("CODE_VERIFY_RATE_LIMIT"))
def verify_email():
    email, purpose = session.get("pending_email"), session.get("pending_purpose")
    if not email or purpose != "verify":
        return _err("Your session has ended. Please sign in again.", 410, restart=True)
    try:
        consume_code(email, "verify", str(_data().get("otp") or "").strip())
    except CodeError as exc:
        return _err(str(exc), 400, expired=exc.restart)
    user = User.query.filter_by(email=email).first()
    if user is None or user.college_id != session.get("pending_college_id") or not user.is_active:
        _clear_pending()
        return _err("Your session has ended. Please sign in again.", 410, restart=True)
    remember = session.get("pending_remember", False)
    user.email_verified_at = user.email_verified_at or utcnow()
    user.last_login_at = utcnow()
    audit("auth.email_verified", user, actor=user)
    db.session.commit()
    _clear_pending()
    login_user(user, remember=remember)
    return _signed_in_json(user)


# ---------------------------------------------------------------- password reset

@bp.route("/forgot", methods=["POST"])
@limiter.limit(_limit("CODE_REQUEST_RATE_LIMIT"))
def forgot():
    f = _data()
    try:
        college = active_college(f.get("college_id"), listed=False)
        email = college_email(f.get("email"), college)
    except OnboardingError as exc:
        return _err(str(exc), exc.status, field=exc.field)
    user = User.query.filter_by(email=email).first()
    if user is not None and user.is_active and user.college_id == college.id:
        if issue_code(email, "reset", college):
            audit("auth.reset_requested", user, actor=user)
            db.session.commit()
    _start_pending(email, "reset", college)   # same response either way
    return _code_sent(email, "reset")


@bp.route("/reset", methods=["POST"])
@limiter.limit(_limit("CODE_VERIFY_RATE_LIMIT"))
def reset():
    email, purpose = session.get("pending_email"), session.get("pending_purpose")
    if not email or purpose != "reset":
        return _err("Your session has ended. Please start again.", 410, restart=True)
    f = _data()
    password = f.get("password")
    if password != f.get("confirm_password"):
        return _err("The passwords don't match.", 400, field="confirm_password")
    user = User.query.filter_by(email=email).first()
    try:
        check_new_password(password, email, user.student_id if user and user.student_id else "")
    except OnboardingError as exc:
        return _err(str(exc), exc.status, field=exc.field)
    try:
        consume_code(email, "reset", str(f.get("otp") or "").strip())
    except CodeError as exc:
        return _err(str(exc), 400, expired=exc.restart)
    if user is None or user.college_id != session.get("pending_college_id"):
        _clear_pending()
        return _err("Your session has ended. Please start again.", 410, restart=True)
    user.password = generate_password_hash(password)
    user.session_version += 1           # sign out every other session
    user.failed_login_count, user.locked_until = 0, None
    user.email_verified_at = user.email_verified_at or utcnow()
    audit("auth.password_reset", user, actor=user)
    db.session.commit()
    _clear_pending()
    return jsonify({"status": "password_updated"})
