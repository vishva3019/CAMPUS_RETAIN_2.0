"""Authentication state, role-based permissions and tenant scoping.

Every protected view uses ``login_required`` / ``permission_required``. Every
query for college data uses ``tenant_query`` or ``get_tenant_object``, which
filter on the *authenticated user's* college, never on a value from the request.
"""
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for

from .extensions import db
from .models import College, CollegeStatus, Permission, Role, User

# ---------------------------------------------------------------- roles

PLATFORM_SUPER_ADMIN = "platform_super_admin"
COLLEGE_ADMIN = "college_admin"
CAMPUS_MODERATOR = "campus_moderator"
SECURITY_STAFF = "security_staff"
STUDENT = "student"

PERMISSIONS = {
    "items.view": "Browse items in own college",
    "items.report": "Report found or lost items",
    "claims.submit": "Submit ownership claims",
    "items.manage": "Edit and remove item listings",
    "claims.review": "Approve or reject claims",
    "collection.verify": "Verify pickup codes and confirm handovers",
    "users.manage": "Manage students and staff in own college",
    "college.settings": "Configure college branding, campuses and collection points",
    "analytics.view": "View college analytics and exports",
    "audit.view": "View audit logs",
    "platform.manage": "Manage colleges, subscriptions and platform settings",
}

ROLES = {
    PLATFORM_SUPER_ADMIN: ("Platform Super Admin", True, {"platform.manage", "audit.view"}),
    COLLEGE_ADMIN: ("College Admin", False, {
        "items.view", "items.report", "items.manage", "claims.review", "collection.verify",
        "users.manage", "college.settings", "analytics.view", "audit.view",
    }),
    CAMPUS_MODERATOR: ("Campus Moderator", False, {"items.view", "items.report", "items.manage", "claims.review"}),
    SECURITY_STAFF: ("Security Staff", False, {"items.view", "collection.verify"}),
    STUDENT: ("Student", False, {"items.view", "items.report", "claims.submit"}),
}

STAFF_ROLES = (COLLEGE_ADMIN, CAMPUS_MODERATOR, SECURITY_STAFF)


def sync_roles():
    """Create/update roles and permissions from the definitions above. Idempotent."""
    perms = {p.code: p for p in Permission.query.all()}
    for code, description in PERMISSIONS.items():
        if code not in perms:
            perms[code] = Permission(code=code, description=description)
            db.session.add(perms[code])
        else:
            perms[code].description = description
    for name, (label, is_platform, codes) in ROLES.items():
        role = Role.query.filter_by(name=name).first()
        if not role:
            role = Role(name=name, label=label, is_platform=is_platform)
            db.session.add(role)
        role.label, role.is_platform = label, is_platform
        role.permissions = [perms[c] for c in sorted(codes)]
    db.session.commit()


def get_role(name):
    role = Role.query.filter_by(name=name).first()
    if role is None:
        raise RuntimeError(f"Role '{name}' missing. Run 'flask db upgrade' (or 'flask rbac sync').")
    return role


# ---------------------------------------------------------------- session

def login_user(user, remember=False):
    """Start a fresh session (prevents fixation) bound to the user's session_version.

    remember=True keeps a student signed in for REMEMBER_DAYS with a persistent cookie.
    Otherwise the cookie lasts until the browser closes, and at most SESSION_HOURS."""
    import time

    from flask import current_app

    cfg = current_app.config
    remember = bool(remember) and user.role_name == STUDENT
    session.clear()
    session.permanent = remember
    session["uid"] = user.id
    session["sv"] = user.session_version
    hours = cfg["REMEMBER_DAYS"] * 24 if remember else cfg["SESSION_HOURS"]
    session["exp"] = int(time.time()) + hours * 3600
    session["greet"] = True   # the app shows its welcome animation once after this sign-in


def logout_user():
    session.clear()


def load_current_user():
    """before_request hook: resolve g.user and g.college from the session."""
    g.user = None
    g.college = None
    uid = session.get("uid")
    if not uid:
        return
    import time

    from flask import current_app
    now = int(time.time())
    if "exp" not in session:          # sessions from before expiry was stored server-side
        session["exp"] = now + current_app.config["SESSION_HOURS"] * 3600
    if session["exp"] < now:
        session.clear()
        return
    user = db.session.get(User, uid)
    if (user is None or not user.is_active or session.get("sv") != user.session_version
            or not user.is_verified):
        session.clear()
        return
    if user.college_id is not None:
        college = user.college
        if college is None or college.status != CollegeStatus.ACTIVE:
            session.clear()
            g.college_suspended = True
            return
        g.college = college
    g.user = user


def _wants_json():
    return request.path.startswith("/api/")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.get("user") is None:
            if _wants_json():
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
        return view(*args, **kwargs)
    return wrapper


def permission_required(*codes):
    """Require ALL listed permissions. Platform admins have no college permissions."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            user = g.user
            if not all(user.has_permission(c) for c in codes):
                if _wants_json():
                    return jsonify({"error": "You do not have permission for this action."}), 403
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def college_member_required(view):
    """Views that need a college context (everything except the platform console)."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if g.get("college") is None:
            if _wants_json():
                return jsonify({"error": "This action needs a college account."}), 403
            abort(403)
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- tenant scoping

def tenant_query(model):
    """Query restricted to the current user's college (and campus for campus-bound moderators)."""
    user = g.get("user")
    if user is None or user.college_id is None:
        abort(403)
    query = model.query.filter(model.college_id == user.college_id)
    if (user.role_name == CAMPUS_MODERATOR and user.campus_id is not None
            and hasattr(model, "campus_id")):
        query = query.filter(model.campus_id == user.campus_id)
    return query


def get_tenant_object(model, object_id):
    """Fetch by id inside the current tenant; 404 (not 403) for other colleges' ids,
    so the existence of foreign records is not revealed."""
    obj = tenant_query(model).filter(model.id == object_id).first()
    if obj is None:
        if _wants_json():
            abort(404)
        abort(404)
    return obj


def college_for_email(email):
    """Match an email address to an ACTIVE college by its registered domains.
    Subdomains match too (student@cse.example.edu matches example.edu)."""
    from .models import CollegeDomain

    if "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].lower()
    candidates = [domain]
    parts = domain.split(".")
    candidates += [".".join(parts[i:]) for i in range(1, len(parts) - 1)]
    match = (CollegeDomain.query.filter(CollegeDomain.domain.in_(candidates))
             .join(College).filter(College.status == CollegeStatus.ACTIVE)
             .order_by(db.func.length(CollegeDomain.domain).desc()).first())
    return match.college if match else None
