from datetime import timedelta

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models import (Claim, College, CollegeStatus, CollectionPoint, Item, ItemKind,
                      ItemStatus, Notification, utcnow)
from ..security import college_member_required, permission_required, tenant_query
from ..services.claims import ClaimError, close_lost_report, resend_pickup_code, withdraw_claim

bp = Blueprint("student", __name__)


@bp.route("/")
def index():
    if g.get("user"):
        from .auth import _home_for
        return redirect(_home_for(g.user))
    from flask import current_app

    from .spa import index_html, spa_available
    if current_app.config.get("USE_REACT_APP") and spa_available():
        return index_html()   # the animated welcome and onboarding (React)
    colleges = (College.query.filter_by(status=CollegeStatus.ACTIVE)
                .order_by(College.name).all())
    return render_template("index.html", colleges=colleges)


def escape_like(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def visible_items_query(kind=ItemKind.FOUND):
    """Items a college member may browse. Found items: everything not removed. Lost
    reports: only those still open. Secret details are never rendered on student pages."""
    statuses = ItemStatus.VISIBLE if kind == ItemKind.FOUND else (ItemStatus.AVAILABLE,)
    query = (tenant_query(Item).filter(Item.kind == kind, Item.status.in_(statuses))
             .options(selectinload(Item.images), joinedload(Item.collection_point)))
    q = request.args.get("q", "").strip()[:100]
    relevance = None
    if q:
        from ..services.matching import search_filter
        query, relevance = search_filter(query, q)
    category = request.args.get("category", "").strip()
    if category:
        query = query.filter(Item.category == category)
    if kind == ItemKind.FOUND:
        # open = not yet handed back; available = can be claimed now; returned; all (default)
        availability = {"open": (ItemStatus.AVAILABLE, ItemStatus.PENDING, ItemStatus.CLAIMED),
                        "available": (ItemStatus.AVAILABLE,), "returned": (ItemStatus.RETURNED,)}
        wanted = availability.get(request.args.get("availability", ""))
        if wanted:
            query = query.filter(Item.status.in_(wanted))
    campus_id = request.args.get("campus", type=int)
    if campus_id:
        query = query.filter(Item.campus_id == campus_id)
    since = request.args.get("since", type=int)
    if since in (1, 7, 30, 90, 365):
        query = query.filter(Item.date_found >= utcnow() - timedelta(days=since))
    place = request.args.get("place", "").strip()[:100]
    if place:
        query = query.filter(Item.location.ilike(f"%{escape_like(place)}%", escape="\\"))
    event_id = request.args.get("event", type=int)
    if event_id:
        query = query.filter(Item.event_id == event_id)
    order = ([relevance.desc()] if relevance is not None else []) + [Item.date_found.desc(), Item.id.desc()]
    return query.order_by(*order), q


@bp.route("/dashboard")
@college_member_required
@permission_required("items.view")
def dashboard():
    view = request.args.get("view", ItemKind.FOUND)
    if view not in (ItemKind.FOUND, ItemKind.LOST):
        view = ItemKind.FOUND
    query, q = visible_items_query(view)
    page = query.paginate(
        page=request.args.get("page", 1, type=int),
        per_page=current_app.config["PAGE_SIZE"], error_out=False)
    points = (CollectionPoint.query.filter_by(college_id=g.college.id, is_active=True)
              .order_by(CollectionPoint.name).all())
    unread = Notification.query.filter_by(user_id=g.user.id, read_at=None).count()
    return render_template("dashboard.html", items=page.items, pagination=page, q=q, view=view,
                           points=points, unread=unread,
                           today=utcnow().date().isoformat(),
                           user_email=g.user.email, college=g.college,
                           can_report=g.user.has_permission("items.report"),
                           can_claim=g.user.has_permission("claims.submit"),
                           can_desk=g.user.has_permission("collection.verify"),
                           is_staff=any(g.user.has_permission(p) for p in
                                        ("claims.review", "items.manage", "collection.verify")))


# ---------------------------------------------------------------- my activity

@bp.route("/me")
@college_member_required
def activity():
    from ..rls import rls_bypass
    with rls_bypass():
        return _activity()


def _activity():
    user = g.user
    claims = (Claim.query.filter_by(claimant_id=user.id)
              .options(joinedload(Claim.item).joinedload(Item.collection_point))
              .order_by(Claim.timestamp.desc()).limit(50).all())
    reports = (Item.query.filter(Item.reported_by_id == user.id, Item.college_id == user.college_id,
                                 Item.status != ItemStatus.REMOVED)
               .options(selectinload(Item.images))
               .order_by(Item.date_found.desc()).limit(50).all())
    notes = (Notification.query.filter_by(user_id=user.id)
             .order_by(Notification.created_at.desc()).limit(30).all())
    unread_ids = [n.id for n in notes if n.read_at is None]
    page = render_template("activity.html", claims=claims, reports=reports, notes=notes,
                           unread_ids=set(unread_ids), college=g.college)
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {"read_at": utcnow()}, synchronize_session=False)
        db.session.commit()
    return page


@bp.route("/me/claims/<int:claim_id>/pickup-code", methods=["POST"])
@college_member_required
def new_pickup_code(claim_id):
    try:
        resend_pickup_code(g.user, claim_id)
    except ClaimError as exc:
        flash(str(exc), "error")
    else:
        flash("A new pickup code was sent to your email. Earlier codes no longer work.", "success")
    return redirect(url_for("student.activity"))


@bp.route("/me/claims/<int:claim_id>/withdraw", methods=["POST"])
@college_member_required
def withdraw_claim_view(claim_id):
    try:
        claim = withdraw_claim(g.user, claim_id)
    except ClaimError as exc:
        if exc.status == 404:
            abort(404)
        flash(str(exc), "error")
    else:
        flash(f"Claim for {claim.item.name} withdrawn.", "success")
    return redirect(url_for("student.activity"))


@bp.route("/me/lost/<int:item_id>/<action>", methods=["POST"])
@college_member_required
def close_lost_report_view(item_id, action):
    try:
        close_lost_report(g.user, item_id, action)
    except ClaimError as exc:
        flash(str(exc), "error")
    else:
        flash("Glad you got it back!" if action == "found" else "Lost-item report removed.", "success")
    return redirect(url_for("student.activity"))
