"""Pickup desk for security staff and college admins: hand items over only after
checking the claimant's one-time pickup code."""
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ..models import Claim, ClaimStatus, Item, ItemStatus
from ..security import college_member_required, permission_required, tenant_query
from ..services.claims import ClaimError, verify_pickup
from .student import escape_like

bp = Blueprint("desk", __name__, url_prefix="/desk")


def _awaiting_query():
    query = (tenant_query(Claim).filter(Claim.status == ClaimStatus.APPROVED)
             .join(Item, Item.id == Claim.item_id)
             .filter(Item.status == ItemStatus.CLAIMED)
             .options(joinedload(Claim.item)))
    user = g.user
    if user.role_name == "security_staff" and user.campus_id:
        query = query.filter(or_(Item.campus_id == user.campus_id, Item.campus_id.is_(None)))
    return query


def desk_query(q):
    query = _awaiting_query()
    if q:
        like = f"%{escape_like(q)}%"
        query = query.filter(or_(Item.name.ilike(like, escape="\\"),
                                 Claim.student_email.ilike(like, escape="\\"),
                                 Claim.student_id.ilike(like, escape="\\")))
    return query.order_by(Claim.reviewed_at.desc())


def recent_handovers(limit=10):
    return (tenant_query(Claim).filter(Claim.status == ClaimStatus.COLLECTED)
            .options(joinedload(Claim.item), joinedload(Claim.collected_by))
            .order_by(Claim.collected_at.desc()).limit(limit).all())


@bp.route("/")
@college_member_required
@permission_required("collection.verify")
def index():
    q = request.args.get("q", "").strip()[:100]
    page = desk_query(q).paginate(page=request.args.get("page", 1, type=int),
                                  per_page=current_app.config["PAGE_SIZE"], error_out=False)
    recent = recent_handovers()
    return render_template("desk.html", claims=page.items, pagination=page, q=q,
                           recent=recent, college=g.college,
                           max_attempts=current_app.config["PICKUP_CODE_MAX_ATTEMPTS"])


@bp.route("/verify/<int:claim_id>", methods=["POST"])
@college_member_required
@permission_required("collection.verify")
def verify(claim_id):
    try:
        claim = verify_pickup(g.user, claim_id, request.form.get("code"))
    except ClaimError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Handed over: {claim.item.name} to {claim.student_email}.", "success")
    return redirect(url_for("desk.index", q=request.args.get("q") or None))
