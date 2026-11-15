"""Platform Super Admin console: onboard, activate and suspend colleges; invite college admins."""
import re

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from ..extensions import db
from ..models import College, CollegeDomain, CollegeStatus, Item, ItemStatus, User
from ..security import COLLEGE_ADMIN, get_role, permission_required
from ..services.audit import audit
from ..services.messaging import send_email

bp = Blueprint("platform", __name__, url_prefix="/platform")

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$")
DOMAIN_RE = re.compile(r"^(?=.{4,160}$)([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")


def parse_domains(raw):
    domains = sorted({d.strip().lower().lstrip("@") for d in re.split(r"[\s,]+", raw or "") if d.strip()})
    bad = [d for d in domains if not DOMAIN_RE.match(d)]
    return domains, bad


def create_college(name, slug, domains, actor=None, **fields):
    """Shared by the console and the CLI. Raises ValueError with a user-facing message."""
    name, slug = (name or "").strip(), (slug or "").strip().lower()
    if not name or len(name) > 160:
        raise ValueError("College name is required (max 160 characters).")
    if not SLUG_RE.match(slug):
        raise ValueError("Slug must be lowercase letters, numbers and dashes (e.g. mvj-ce).")
    if College.query.filter_by(slug=slug).first():
        raise ValueError(f"The slug '{slug}' is already used.")
    if not domains:
        raise ValueError("Add at least one email domain.")
    taken = CollegeDomain.query.filter(CollegeDomain.domain.in_(domains)).all()
    if taken:
        raise ValueError("Already registered to another college: " + ", ".join(t.domain for t in taken))
    college = College(name=name, slug=slug, status=fields.pop("status", CollegeStatus.PENDING),
                      **{k: (v or None) for k, v in fields.items()})
    college.domains = [CollegeDomain(domain=d) for d in domains]
    db.session.add(college)
    db.session.flush()
    audit("college.created", college, college_id=college.id, actor=actor, domains=domains)
    return college


def platform_overview():
    colleges = College.query.order_by(College.created_at.desc()).all()
    students = dict(db.session.query(User.college_id, func.count(User.id)).group_by(User.college_id).all())
    items = dict(db.session.query(Item.college_id, func.count(Item.id))
                 .filter(Item.status != ItemStatus.REMOVED).group_by(Item.college_id).all())
    returned = dict(db.session.query(Item.college_id, func.count(Item.id))
                    .filter(Item.status.in_((ItemStatus.CLAIMED, ItemStatus.RETURNED)))
                    .group_by(Item.college_id).all())
    admins = {}
    for u in (User.query.join(User.role).filter_by(name=COLLEGE_ADMIN).order_by(User.email).all()):
        admins.setdefault(u.college_id, []).append(u)
    return dict(colleges=colleges, students=students, items=items, returned=returned, admins=admins)


def invite_college_admin(college, email, actor=None):
    """Create an unverified College Admin who sets a password via 'Forgot password?'.
    Raises ValueError with a user-facing message. Commits."""
    from .auth import random_unusable_password

    email = (email or "").strip().lower()
    if not email or "@" not in email or len(email) > 120:
        raise ValueError("Enter a valid email address.")
    if User.query.filter_by(email=email).first():
        raise ValueError("That email already has an account.")
    user = User(email=email, college_id=college.id, role_id=get_role(COLLEGE_ADMIN).id,
                password=random_unusable_password())
    db.session.add(user)
    db.session.flush()
    audit("user.invited", user, college_id=college.id, actor=actor, role=COLLEGE_ADMIN)
    db.session.commit()
    login_url = url_for("auth.login", _external=True)
    send_email(email, f"You're an administrator for {college.name} on Campus Retain",
               f"Hello,\n\nYou have been added as a College Admin for {college.name}.\n\n"
               f"To set your password, open {login_url}, choose 'Forgot password?' and enter this email. "
               "You will get a one-time code.", college=college)
    return user


def change_college_status(college, status, actor=None):
    if status not in CollegeStatus.ALL:
        raise ValueError("Unknown status.")
    old, college.status = college.status, status
    audit("college.status_changed", college, college_id=college.id, actor=actor, old=old, new=status)
    db.session.commit()


@bp.route("/")
@permission_required("platform.manage")
def home():
    return render_template("platform.html", statuses=CollegeStatus.ALL, **platform_overview())


@bp.route("/colleges", methods=["POST"])
@permission_required("platform.manage")
def add_college():
    f = request.form
    domains, bad = parse_domains(f.get("domains"))
    if bad:
        flash("Invalid domain: " + ", ".join(bad), "error")
        return redirect(url_for(".home"))
    try:
        college = create_college(
            f.get("name"), f.get("slug"), domains, actor=g.user,
            short_name=f.get("short_name", "").strip()[:40], city=f.get("city", "").strip()[:80],
            contact_email=f.get("contact_email", "").strip().lower()[:160],
            support_office=f.get("support_office", "").strip()[:160],
            pickup_instructions=f.get("pickup_instructions", "").strip()[:2000],
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for(".home"))
    db.session.commit()
    flash(f"{college.name} added as pending. Activate it when it is verified.", "success")
    return redirect(url_for(".home"))


@bp.route("/colleges/<int:college_id>/status", methods=["POST"])
@permission_required("platform.manage")
def set_status(college_id):
    college = db.get_or_404(College, college_id)
    try:
        change_college_status(college, request.form.get("status"), actor=g.user)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for(".home"))
    flash(f"{college.name} is now {college.status}.", "success")
    return redirect(url_for(".home"))


@bp.route("/colleges/<int:college_id>/admins", methods=["POST"])
@permission_required("platform.manage")
def invite_admin(college_id):
    college = db.get_or_404(College, college_id)
    try:
        user = invite_college_admin(college, request.form.get("email"), actor=g.user)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for(".home"))
    flash(f"Invited {user.email}. They set a password with 'Forgot password?'.", "success")
    return redirect(url_for(".home"))
