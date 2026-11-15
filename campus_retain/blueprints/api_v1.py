"""JSON API for the React frontend (``/api/v1``).

Same rules as the server-rendered pages: session cookie auth, CSRF header on every
POST, permissions checked here, and every query scoped to the user's college. Write
actions that already existed (report, claim, approve, reject, remove, move to a
collection point) keep their ``/api/...`` paths and are reused by the frontend.
"""
import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, current_app, g, jsonify, make_response, request, session
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db, limiter
from ..models import (Campus, Claim, ClaimStatus, College, CollegeStatus, CollectionPoint, Item, ItemKind,
                      ItemStatus, Notification, utcnow)
from ..security import college_member_required, login_required, permission_required, tenant_query
from ..serializers import (day, desk_claim_json, finder_note, iso, item_json, my_claim_json, notification_json,
                           page_json, point_json, staff_claim_json)
from ..services.audit import audit
from ..services.claims import (ClaimError, close_lost_report, resend_pickup_code, verify_pickup,
                               withdraw_claim)
from .admin import (STAFF_PERMISSIONS, admin_counts, admin_items_query, create_collection_point,
                    points_held, toggle_point)
from ..services.plans import plan_gate
from .api import CATEGORIES
from .desk import desk_query, recent_handovers
from .platform import (change_college_status, create_college, invite_college_admin, parse_domains,
                       platform_overview)
from .student import visible_items_query

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _err(message, status=400):
    return jsonify({"error": message}), status


def _paginate(query):
    per_page = min(max(request.args.get("per_page", current_app.config["PAGE_SIZE"], type=int), 1), 100)
    return query.paginate(page=max(request.args.get("page", 1, type=int), 1), per_page=per_page,
                          error_out=False)


def _staff_required():
    if not any(g.user.has_permission(p) for p in STAFF_PERMISSIONS):
        abort(403)


# ---------------------------------------------------------------- session

@bp.route("/session")
@login_required
def session_info():
    user, college = g.user, g.get("college")
    perms = sorted(user.role.permission_codes()) if user.role else []
    data = {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name,
                 "role": user.role_name, "role_label": user.role.label if user.role else None,
                 "campus": user.campus.name if user.campus else None, "permissions": perms,
                 "student_id": user.student_id},
        "college": None,
        "csrf_token": generate_csrf(),
        "config": {"max_photos": current_app.config["MAX_PHOTOS_PER_ITEM"],
                   "max_image_mb": current_app.config["MAX_IMAGE_BYTES"] // (1024 * 1024),
                   "categories": list(CATEGORIES),
                   "pickup_code_max_attempts": current_app.config["PICKUP_CODE_MAX_ATTEMPTS"]},
        "unread": 0,
        # True only on the first session load after signing in (shows the welcome animation once).
        "greet": bool(session.pop("greet", False)),
    }
    from ..services.ai import ai_enabled
    from ..services.plans import feature_allowed, plan_json
    data["config"]["ai_enabled"] = bool(college) and ai_enabled() and feature_allowed(college, "ai")
    if college is not None:
        data["college"] = {
            "id": college.id, "slug": college.slug, "name": college.name,
            "display_name": college.display_name, "primary_color": college.primary_color,
            "support_office": college.support_office, "contact_email": college.contact_email,
            "campuses": [{"id": c.id, "name": c.name} for c in college.campuses if c.is_active],
            "network": bool(college.inter_college_matching),
        }
        data["unread"] = Notification.query.filter_by(user_id=user.id, read_at=None).count()
        data["college"]["plan"] = plan_json(college)
        data["college"]["network"] = data["college"]["network"] and feature_allowed(college, "network")
    return jsonify(data)


# ---------------------------------------------------------------- browse

@bp.route("/items")
@college_member_required
@permission_required("items.view")
def items():
    kind = request.args.get("kind", ItemKind.FOUND)
    if kind not in (ItemKind.FOUND, ItemKind.LOST):
        return _err("Unknown item type.")
    query, _q = visible_items_query(kind)
    page = _paginate(query)
    return jsonify(page_json(page, [item_json(i) for i in page.items]))


@bp.route("/items/<int:item_id>")
@college_member_required
@permission_required("items.view")
def item_detail(item_id):
    """One item as students see it (never the private detail or the reporter's contact)."""
    item = (tenant_query(Item).filter(Item.id == item_id, Item.status != ItemStatus.REMOVED)
            .options(selectinload(Item.images), joinedload(Item.collection_point)).first())
    if item is None or (item.kind == ItemKind.LOST and item.status != ItemStatus.AVAILABLE
                        and item.reported_by_id != g.user.id):
        return _err("That item isn't available any more.", 404)
    data = item_json(item)
    mine = (Claim.query.filter_by(item_id=item.id, claimant_id=g.user.id)
            .order_by(Claim.timestamp.desc()).first())
    data["my_claim"] = ({"id": mine.id, "status": mine.status, "timestamp": iso(mine.timestamp)}
                        if mine else None)
    return jsonify(data)


@bp.route("/items/similar")
@college_member_required
@permission_required("items.report")
def items_similar():
    """Shown in the report form before posting: 'Already reported? These look similar.'"""
    from ..services.matching import find_duplicates
    a = request.args
    kind = a.get("kind", ItemKind.FOUND)
    if kind not in (ItemKind.FOUND, ItemKind.LOST):
        return _err("Unknown item type.")
    rows = find_duplicates(g.college.id, kind, a.get("name", "")[:120], a.get("category"),
                           a.get("location", "")[:150], a.get("description", "")[:500])
    return jsonify({"items": [dict(item_json(i), score=s) for i, s, _r in rows]})


@bp.route("/me/matches")
@college_member_required
def my_matches():
    """Found items that may be one of my open lost reports."""
    from ..models import ItemMatch, MatchStatus
    from ..serializers import match_json
    rows = (ItemMatch.query.join(Item, Item.id == ItemMatch.lost_item_id)
            .filter(Item.reported_by_id == g.user.id, Item.college_id == g.user.college_id,
                    Item.status == ItemStatus.AVAILABLE, ItemMatch.status == MatchStatus.SUGGESTED)
            .order_by(ItemMatch.score.desc()).limit(50).all())
    visible = [m for m in rows if m.found_item.status in (ItemStatus.AVAILABLE, ItemStatus.PENDING)]
    return jsonify({"items": [dict(match_json(m, "found"), lost_item_id=m.lost_item_id,
                                   lost_item_name=m.lost_item.name) for m in visible]})


@bp.route("/matches/<int:match_id>/dismiss", methods=["POST"])
@college_member_required
def dismiss_match(match_id):
    from ..models import ItemMatch, MatchStatus
    m = (ItemMatch.query.join(Item, Item.id == ItemMatch.lost_item_id)
         .filter(ItemMatch.id == match_id, Item.reported_by_id == g.user.id,
                 ItemMatch.college_id == g.user.college_id).first())
    if m is None:
        return _err("Match not found.", 404)
    m.status = MatchStatus.DISMISSED
    audit("match.dismissed", m, college_id=m.college_id)
    db.session.commit()
    return jsonify({"status": "success"})


@bp.route("/admin/items/<int:item_id>/matches")
@college_member_required
@permission_required("claims.review")
def admin_item_matches(item_id):
    from ..models import ItemMatch, MatchStatus
    from ..security import get_tenant_object
    from ..serializers import match_json
    item = get_tenant_object(Item, item_id)
    col = ItemMatch.found_item_id if item.kind == ItemKind.FOUND else ItemMatch.lost_item_id
    rows = (ItemMatch.query.filter(col == item.id, ItemMatch.status != MatchStatus.DISMISSED)
            .order_by(ItemMatch.score.desc()).limit(10).all())
    side = "lost" if item.kind == ItemKind.FOUND else "found"
    return jsonify({"items": [match_json(m, side) for m in rows]})


@bp.route("/collection-points")
@college_member_required
def collection_points():
    points = (CollectionPoint.query.filter_by(college_id=g.college.id, is_active=True)
              .options(joinedload(CollectionPoint.campus)).order_by(CollectionPoint.name).all())
    return jsonify({"items": [point_json(p) for p in points]})


# ---------------------------------------------------------------- my activity

@bp.route("/me/activity")
@college_member_required
def my_activity():
    from ..rls import rls_bypass
    with rls_bypass():   # network claims belong to other colleges; filtered by claimant below
        return _my_activity()


def _my_activity():
    user = g.user
    claims = (Claim.query.filter_by(claimant_id=user.id)
              .options(joinedload(Claim.item).joinedload(Item.collection_point),
                       joinedload(Claim.item).selectinload(Item.images))
              .order_by(Claim.timestamp.desc()).limit(100).all())
    reports = (Item.query.filter(Item.reported_by_id == user.id, Item.college_id == user.college_id,
                                 Item.status != ItemStatus.REMOVED)
               .options(selectinload(Item.images), joinedload(Item.collection_point))
               .order_by(Item.date_found.desc()).limit(100).all())
    return jsonify({"claims": [my_claim_json(c, c.item.college) for c in claims],
                    "reports": [item_json(i) for i in reports]})


def _claim_action(fn, *args):
    try:
        fn(g.user, *args)
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    return jsonify({"status": "success"})


@bp.route("/me/claims/<int:claim_id>/pickup-code", methods=["POST"])
@college_member_required
def my_pickup_code(claim_id):
    """Issue a fresh pickup code: emailed, and shown once to the signed-in claimant."""
    try:
        claim = resend_pickup_code(g.user, claim_id)
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    resp = jsonify({"status": "success", "code": getattr(claim, "issued_code", None),
                    "expires_at": iso(claim.pickup_code_expires_at)})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/me/claims/<int:claim_id>/withdraw", methods=["POST"])
@college_member_required
def my_withdraw(claim_id):
    return _claim_action(withdraw_claim, claim_id)


@bp.route("/me/lost/<int:item_id>/<action>", methods=["POST"])
@college_member_required
def my_lost(item_id, action):
    return _claim_action(close_lost_report, item_id, action)


# ---------------------------------------------------------------- notifications

@bp.route("/notifications")
@college_member_required
def notifications():
    query = Notification.query.filter_by(user_id=g.user.id)
    if request.args.get("unread") == "1":
        query = query.filter(Notification.read_at.is_(None))
    page = _paginate(query.order_by(Notification.created_at.desc(), Notification.id.desc()))
    data = page_json(page, [notification_json(n) for n in page.items])
    data["unread"] = Notification.query.filter_by(user_id=g.user.id, read_at=None).count()
    return jsonify(data)


@bp.route("/notifications/read", methods=["POST"])
@college_member_required
def notifications_read():
    body = request.get_json(silent=True) or {}
    query = Notification.query.filter(Notification.user_id == g.user.id, Notification.read_at.is_(None))
    ids = body.get("ids")
    if ids is not None:
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return _err("ids must be a list of numbers.")
        query = query.filter(Notification.id.in_(ids))
    changed = query.update({"read_at": utcnow()}, synchronize_session=False)
    db.session.commit()
    unread = Notification.query.filter_by(user_id=g.user.id, read_at=None).count()
    return jsonify({"status": "success", "marked": changed, "unread": unread})


# ---------------------------------------------------------------- staff

@bp.route("/admin/items")
@college_member_required
def admin_items():
    _staff_required()
    query, _q, _status, _kind = admin_items_query(request.args)
    page = _paginate(query)
    data = page_json(page, [item_json(i, staff=True) for i in page.items])
    data["counts"] = admin_counts()
    return jsonify(data)


def _csv_cell(value):
    """Neutralise spreadsheet formulas (CSV injection) in user-entered text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/admin/claims")
@college_member_required
@permission_required("claims.review")
def admin_claims():
    """Claims waiting for review, oldest first, with what a reviewer needs side by side:
    the item (including the private detail), the claimant's proof, warnings, and history."""
    from ..services.matching import claim_flags
    from ..security import CAMPUS_MODERATOR
    query = (tenant_query(Claim).filter(Claim.status == ClaimStatus.PENDING)
             .join(Item, Item.id == Claim.item_id)
             .options(joinedload(Claim.item).selectinload(Item.images),
                      joinedload(Claim.item).selectinload(Item.claims)))
    if g.user.role_name == CAMPUS_MODERATOR and g.user.campus_id:
        query = query.filter(or_(Item.campus_id == g.user.campus_id, Item.campus_id.is_(None)))
    page = _paginate(query.order_by(Claim.timestamp.asc(), Claim.id.asc()))
    out = []
    for c in page.items:
        data = staff_claim_json(c)
        data["flags"] = claim_flags(c)
        data["item"] = item_json(c.item, staff=True)
        data["claimant_history"] = {
            s: n for s, n in db.session.query(Claim.status, func.count(Claim.id))
            .filter(Claim.claimant_id == c.claimant_id, Claim.id != c.id).group_by(Claim.status).all()
        } if c.claimant_id else {}
        out.append(data)
    return jsonify(page_json(page, out))


@bp.route("/admin/items.csv")
@college_member_required
@plan_gate("exports")
def admin_items_csv():
    _staff_required()
    if not (g.user.has_permission("items.manage") or g.user.has_permission("claims.review")):
        abort(403)
    query, _q, status_key, kind = admin_items_query(request.args)
    limit = 5000
    rows = query.limit(limit + 1).all()
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(["Item ID", "Type", "Name", "Category", "Location", "Campus", "Status",
                  "Reported at (UTC)", "Date found/lost", "Reported by", "Collection point",
                  "Latest claim status", "Claimant email", "Reviewed by", "Reviewed at (UTC)",
                  "Collected at (UTC)", "Handed over by"])
    for item in rows[:limit]:
        claim = item.claims[-1] if item.claims else None
        out.writerow([_csv_cell(v) for v in [
            item.id, item.kind, item.name, item.category, item.location,
            item.campus.name if item.campus else "", item.status, iso(item.date_found),
            day(item.occurred_on), item.reported_by.email if item.reported_by else "",
            item.collection_point.name if item.collection_point else "",
            claim.status if claim else "", claim.student_email if claim else "",
            claim.reviewed_by.email if claim and claim.reviewed_by else "",
            iso(claim.reviewed_at) if claim else "", iso(claim.collected_at) if claim else "",
            claim.collected_by.email if claim and claim.collected_by else "",
        ]])
    audit("items.exported", None, college_id=g.college.id, kind=kind, status=status_key or "active",
          rows=min(len(rows), limit))
    db.session.commit()
    name = f"campus-retain-{g.college.slug}-{kind}-{utcnow():%Y%m%d}.csv"
    resp = Response("﻿" + buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    if len(rows) > limit:
        resp.headers["X-Truncated"] = str(limit)
    return resp


@bp.route("/admin/collection-points", methods=["GET", "POST"])
@college_member_required
@permission_required("college.settings")
def admin_collection_points():
    college = g.college
    if request.method == "POST":
        try:
            point = create_collection_point(college, request.get_json(silent=True) or {}, actor=g.user)
        except ValueError as exc:
            db.session.rollback()
            return _err(str(exc))
        return jsonify({"status": "success", "point": point_json(point)})
    points = (CollectionPoint.query.filter_by(college_id=college.id)
              .options(joinedload(CollectionPoint.campus))
              .order_by(CollectionPoint.is_active.desc(), CollectionPoint.name).all())
    held = points_held(college)
    campuses = Campus.query.filter_by(college_id=college.id, is_active=True).order_by(Campus.name).all()
    return jsonify({"items": [point_json(p, held) for p in points],
                    "campuses": [{"id": c.id, "name": c.name} for c in campuses]})


@bp.route("/admin/collection-points/<int:point_id>/toggle", methods=["POST"])
@college_member_required
@permission_required("college.settings")
def admin_toggle_point(point_id):
    point = toggle_point(g.college, point_id, actor=g.user)
    return jsonify({"status": "success", "point": point_json(point)})


@bp.route("/desk")
@college_member_required
@permission_required("collection.verify")
def desk():
    q = request.args.get("q", "").strip()[:100]
    page = _paginate(desk_query(q))
    data = page_json(page, [desk_claim_json(c) for c in page.items])
    data["recent"] = [desk_claim_json(c) for c in recent_handovers()]
    return jsonify(data)


@bp.route("/desk/<int:claim_id>/verify", methods=["POST"])
@college_member_required
@permission_required("collection.verify")
def desk_verify(claim_id):
    code = (request.get_json(silent=True) or {}).get("code")
    try:
        claim = verify_pickup(g.user, claim_id, code if isinstance(code, str) else "")
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    return jsonify({"status": "success", "claim": desk_claim_json(claim)})


# ---------------------------------------------------------------- platform

def _college_json(c, overview):
    return {
        "id": c.id, "slug": c.slug, "name": c.name, "short_name": c.short_name, "city": c.city,
        "status": c.status, "domains": [d.domain for d in c.domains], "created_at": iso(c.created_at),
        "listed_on_signup": c.listed_on_signup,
        "contact_email": c.contact_email, "support_office": c.support_office,
        "accounts": overview["students"].get(c.id, 0), "items": overview["items"].get(c.id, 0),
        "approved_or_returned": overview["returned"].get(c.id, 0),
        "admins": [{"email": a.email, "invited": not a.is_verified} for a in overview["admins"].get(c.id, [])],
    }


@bp.route("/platform/colleges", methods=["GET", "POST"])
@permission_required("platform.manage")
def platform_colleges():
    if request.method == "POST":
        f = request.get_json(silent=True) or {}
        domains, bad = parse_domains(f.get("domains"))
        if bad:
            return _err("Invalid domain: " + ", ".join(bad))
        try:
            college = create_college(
                f.get("name"), f.get("slug"), domains, actor=g.user,
                short_name=str(f.get("short_name") or "").strip()[:40],
                city=str(f.get("city") or "").strip()[:80],
                contact_email=str(f.get("contact_email") or "").strip().lower()[:160],
                support_office=str(f.get("support_office") or "").strip()[:160],
                pickup_instructions=str(f.get("pickup_instructions") or "").strip()[:2000])
        except ValueError as exc:
            db.session.rollback()
            return _err(str(exc))
        db.session.commit()
        return jsonify({"status": "success", "id": college.id})
    overview = platform_overview()
    colleges = overview["colleges"]
    return jsonify({
        "items": [_college_json(c, overview) for c in colleges],
        "statuses": list(CollegeStatus.ALL),
        "totals": {"colleges": len(colleges),
                   "active": sum(c.status == CollegeStatus.ACTIVE for c in colleges),
                   "pending": sum(c.status == CollegeStatus.PENDING for c in colleges),
                   "accounts": sum(overview["students"].get(c.id, 0) for c in colleges)},
    })


@bp.route("/platform/colleges/<int:college_id>/status", methods=["POST"])
@permission_required("platform.manage")
def platform_college_status(college_id):
    college = db.get_or_404(College, college_id)
    try:
        change_college_status(college, (request.get_json(silent=True) or {}).get("status"), actor=g.user)
    except ValueError as exc:
        return _err(str(exc))
    return jsonify({"status": "success"})


@bp.route("/platform/colleges/<int:college_id>/signup-listing", methods=["POST"])
@permission_required("platform.manage")
def platform_college_listing(college_id):
    """Show or hide a college card on the public sign-up and sign-in screens."""
    college = db.get_or_404(College, college_id)
    listed = (request.get_json(silent=True) or {}).get("listed")
    if not isinstance(listed, bool):
        return _err("Say whether the college should be listed.")
    if listed and not college.domains:
        return _err("Add an email domain before listing this college.")
    college.listed_on_signup = listed
    audit("college.signup_listing", college, college_id=college.id, listed=listed)
    db.session.commit()
    return jsonify({"status": "success", "listed_on_signup": listed})


@bp.route("/platform/colleges/<int:college_id>/admins", methods=["POST"])
@permission_required("platform.manage")
def platform_invite_admin(college_id):
    college = db.get_or_404(College, college_id)
    try:
        user = invite_college_admin(college, (request.get_json(silent=True) or {}).get("email"), actor=g.user)
    except ValueError as exc:
        db.session.rollback()
        return _err(str(exc))
    return jsonify({"status": "success", "email": user.email})


# ---------------------------------------------------------------- analytics (Phase 4)

def _period():
    from ..services.analytics import parse_period
    try:
        return parse_period(request.args)
    except ValueError as exc:
        abort(make_response(jsonify({"error": str(exc)}), 400))


@bp.route("/admin/analytics")
@college_member_required
@permission_required("analytics.view")
@plan_gate("analytics")
def admin_analytics():
    from ..services.analytics import college_analytics
    start, end = _period()
    return jsonify(college_analytics(start, end))


def _download(data, mimetype, name):
    resp = Response(data, mimetype=mimetype)
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@bp.route("/admin/analytics.xlsx")
@college_member_required
@permission_required("analytics.view")
@plan_gate("exports")
def admin_analytics_xlsx():
    from ..services.analytics import college_analytics
    from ..services.reports import analytics_workbook
    start, end = _period()
    data = college_analytics(start, end)
    items = (admin_items_query({"status": "", "kind": "found"})[0].filter(
        Item.date_found >= start, Item.date_found < end).limit(5000).all()
        + admin_items_query({"status": "", "kind": "lost"})[0].filter(
        Item.date_found >= start, Item.date_found < end).limit(5000).all())
    audit("analytics.exported", None, college_id=g.college.id, format="xlsx", period=data["period"])
    db.session.commit()
    return _download(analytics_workbook(g.college, data, items),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     f"campus-retain-{g.college.slug}-{data['period']['from']}-{data['period']['to']}.xlsx")


@bp.route("/admin/analytics.pdf")
@college_member_required
@permission_required("analytics.view")
@plan_gate("exports")
def admin_analytics_pdf():
    from ..services.analytics import college_analytics
    from ..services.reports import analytics_pdf
    start, end = _period()
    data = college_analytics(start, end)
    audit("analytics.exported", None, college_id=g.college.id, format="pdf", period=data["period"])
    db.session.commit()
    return _download(analytics_pdf(g.college, data, g.user.email), "application/pdf",
                     f"campus-retain-{g.college.slug}-report-{data['period']['to']}.pdf")


def _audit_json(entry, with_college=False):
    out = {"id": entry.id, "action": entry.action, "actor": entry.actor_email,
           "target_type": entry.target_type, "target_id": entry.target_id,
           "details": entry.details or {}, "ip_address": entry.ip_address, "created_at": iso(entry.created_at)}
    if with_college:
        out["college_id"] = entry.college_id
    return out


def _audit_query(query):
    from ..models import AuditLog
    action = request.args.get("action", "").strip()[:60]
    if action:
        query = query.filter(AuditLog.action.like(action.replace("%", "").replace("_", "\\_") + "%", escape="\\"))
    actor = request.args.get("actor", "").strip().lower()[:160]
    if actor:
        query = query.filter(AuditLog.actor_email == actor)
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


@bp.route("/admin/audit")
@college_member_required
@permission_required("audit.view")
def admin_audit():
    from ..models import AuditLog
    page = _paginate(_audit_query(AuditLog.query.filter(AuditLog.college_id == g.college.id)))
    actions = [a for (a,) in db.session.query(AuditLog.action).filter(AuditLog.college_id == g.college.id)
               .distinct().order_by(AuditLog.action).all()]
    data = page_json(page, [_audit_json(e) for e in page.items])
    data["actions"] = actions
    return jsonify(data)


@bp.route("/platform/stats")
@permission_required("platform.manage")
def platform_stats():
    from ..models import User
    month = func.date_trunc("month", User.created_at)
    since = utcnow() - timedelta(days=365)
    signups = [{"month": m.strftime("%Y-%m"), "accounts": n} for m, n in
               db.session.query(month, func.count(User.id)).filter(User.created_at >= since)
               .group_by(month).order_by(month).all() if m]
    found = func.sum(db.case((Item.kind == ItemKind.FOUND, 1), else_=0))
    recovered = func.sum(db.case((db.and_(Item.kind == ItemKind.FOUND,
                                          Item.status.in_((ItemStatus.CLAIMED, ItemStatus.RETURNED))), 1), else_=0))
    per_college = []
    for cid, name, n_found, n_rec in (db.session.query(College.id, College.name, found, recovered)
                                      .outerjoin(Item, db.and_(Item.college_id == College.id,
                                                               Item.status != ItemStatus.REMOVED))
                                      .group_by(College.id, College.name).order_by(College.name).all()):
        n_found, n_rec = int(n_found or 0), int(n_rec or 0)
        per_college.append({"college_id": cid, "name": name, "found": n_found, "recovered": n_rec,
                            "recovery_rate": round(n_rec / n_found, 4) if n_found else None})
    total_found = sum(c["found"] for c in per_college)
    total_rec = sum(c["recovered"] for c in per_college)
    return jsonify({"signups_by_month": signups, "colleges": per_college,
                    "totals": {"found": total_found, "recovered": total_rec,
                               "recovery_rate": round(total_rec / total_found, 4) if total_found else None,
                               "accounts": User.query.count()}})


@bp.route("/platform/audit")
@permission_required("platform.manage", "audit.view")
def platform_audit():
    from ..models import AuditLog
    query = AuditLog.query
    college_id = request.args.get("college_id", type=int)
    if college_id:
        query = query.filter(AuditLog.college_id == college_id)
    page = _paginate(_audit_query(query))
    return jsonify(page_json(page, [_audit_json(e, with_college=True) for e in page.items]))


# ---------------------------------------------------------------- AI helpers (Phase 5)

def _ai_key():
    return f"user:{g.user.id}" if g.get("user") else request.remote_addr


@bp.route("/search/smart")
@limiter.limit(lambda: current_app.config["ASSISTANT_RATE_LIMIT"], key_func=_ai_key)
@college_member_required
@permission_required("items.view")
def smart_search_view():
    """'Describe what you lost': a sentence becomes real filters over this college's items."""
    from ..services.assistant import smart_search
    text = request.args.get("q", "").strip()[:300]
    if len(text) < 2:
        return _err("Describe what you lost, e.g. 'black backpack near the library'.")
    items, plan, relaxed, mode = smart_search(text, g.college, list(CATEGORIES))
    if mode == "ai":
        audit("ai.search", None, college_id=g.college.id, length=len(text))
        db.session.commit()
    return jsonify({"items": [item_json(i) for i in items], "plan": plan, "relaxed": relaxed, "mode": mode})


@bp.route("/assistant", methods=["POST"])
@limiter.limit(lambda: current_app.config["ASSISTANT_RATE_LIMIT"], key_func=_ai_key)
@college_member_required
@permission_required("items.view")
def assistant_chat():
    """The Campus Retain AI chatbot. Answers come only from this college's real records."""
    from ..services.assistant import assistant_reply
    body = request.get_json(silent=True) or {}
    raw = body.get("messages")
    if not isinstance(raw, list) or not raw or len(raw) > 12:
        return _err("Send the conversation as a list of up to 12 messages.")
    messages = []
    for m in raw[-10:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            return _err("Each message needs a role (user or assistant) and text.")
        text = m["content"].strip()[:1000]
        if text:
            messages.append({"role": m["role"], "content": text})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if not messages or messages[-1]["role"] != "user":
        return _err("The last message must be from you.")
    reply, items, mode = assistant_reply(g.user, g.college, messages, list(CATEGORIES))
    if mode == "ai":
        audit("ai.assistant", None, college_id=g.college.id, length=len(messages[-1]["content"]))
        db.session.commit()
    return jsonify({"reply": reply, "items": [item_json(i) for i in items], "mode": mode})


@bp.route("/ai/describe", methods=["POST"])
@limiter.limit(lambda: current_app.config["AI_RATE_LIMIT"], key_func=_ai_key)
@college_member_required
@permission_required("items.report")
@plan_gate("ai")
def ai_describe():
    from ..services.ai import AIError, describe_photo
    from ..services.images import ImageError, process_upload
    photo = request.files.get("image")
    if not photo or not photo.filename:
        return _err("Add a photo first.")
    try:
        data, _ct, _w, _h = process_upload(photo)
        result = describe_photo(data, list(CATEGORIES))
    except ImageError as exc:
        return _err(str(exc))
    except AIError as exc:
        return _err(str(exc), exc.status)
    audit("ai.describe", None, college_id=g.college.id, ok=result.is_item_photo)
    db.session.commit()
    if not result.is_item_photo:
        return _err("That photo doesn't look like a lost-and-found item, so no suggestion was made.", 422)
    return jsonify({"name": result.name[:120], "category": result.category, "description": result.description[:2000]})


@bp.route("/matches/<int:match_id>/ai-check", methods=["POST"])
@limiter.limit(lambda: current_app.config["AI_RATE_LIMIT"], key_func=_ai_key)
@college_member_required
@permission_required("claims.review")
@plan_gate("ai")
def ai_check_match(match_id):
    from ..models import ItemMatch
    from ..serializers import match_json
    from ..services.ai import AIError, check_match
    match = ItemMatch.query.filter_by(id=match_id, college_id=g.college.id).first()
    if match is None:
        return _err("Match not found.", 404)
    try:
        check_match(match)
    except AIError as exc:
        return _err(str(exc), exc.status)
    audit("ai.match_check", match, college_id=match.college_id, verdict=match.ai_verdict)
    db.session.commit()
    return jsonify({"status": "success", "match": match_json(match, "lost")})


# ---------------------------------------------------------------- Phase 6: college settings

@bp.route("/admin/settings", methods=["GET", "POST"])
@college_member_required
@permission_required("college.settings")
def admin_settings():
    c = g.college
    if request.method == "POST":
        f = request.get_json(silent=True) or {}
        changes = {}
        for key, limit in (("support_office", 160), ("pickup_instructions", 2000), ("contact_email", 160)):
            if key in f:
                value = str(f.get(key) or "").strip()[:limit] or None
                if key == "contact_email" and value and "@" not in value:
                    return _err("Enter a valid contact email.")
                if getattr(c, key) != value:
                    changes[key] = value
                    setattr(c, key, value)
        if "inter_college_matching" in f:
            value = bool(f["inter_college_matching"])
            if value and not _plan_allows(c, "network"):
                return _err("The inter-college network isn't included in your college's plan.", 403)
            if c.inter_college_matching != value:
                changes["inter_college_matching"] = value
                c.inter_college_matching = value
        if changes:
            audit("college.settings_changed", c, college_id=c.id, **{k: (v if k != "pickup_instructions" else "updated") for k, v in changes.items()})
        db.session.commit()
    return jsonify({"support_office": c.support_office, "pickup_instructions": c.pickup_instructions,
                    "contact_email": c.contact_email, "inter_college_matching": c.inter_college_matching})


def _plan_allows(college, feature):
    """Plan gates arrive in Phase 7; until a plan exists every feature is allowed."""
    try:
        from ..services.plans import feature_allowed
    except ImportError:
        return True
    return feature_allowed(college, feature)


# ---------------------------------------------------------------- Phase 6: inter-college network

@bp.route("/network/items")
@college_member_required
@permission_required("claims.submit")
def network_items():
    from ..rls import rls_bypass
    with rls_bypass():   # deliberate, redacted cross-college read
        return _network_items()


def _network_items():
    from ..services.network import network_item_json, network_open, network_search, opted_in_colleges
    if not network_open(g.college):
        return jsonify({"enabled": False, "items": [], "page": 1, "pages": 0, "total": 0, "colleges": []})
    q = request.args.get("q", "").strip()[:100]
    page = _paginate(network_search(g.college, q or None, request.args.get("category") or None))
    if q:
        audit("network.search", None, college_id=g.college.id, q=q)
        db.session.commit()
    data = page_json(page, [network_item_json(i) for i in page.items])
    data["enabled"] = True
    data["colleges"] = [{"name": c.name, "city": c.city} for c in opted_in_colleges(g.college.id)]
    return jsonify(data)


@bp.route("/network/claims", methods=["POST"])
@college_member_required
@permission_required("claims.submit")
@plan_gate("network")
def network_claim():
    from ..services.network import submit_network_claim
    data = request.get_json(silent=True) or {}
    student_id = str(data.get("student_id") or "").strip()[:50]
    proof = str(data.get("proof_description") or "").strip()[:2000]
    if not student_id or not proof:
        return _err("Student ID and proof of ownership are required.")
    try:
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError):
        return _err("Invalid item.")
    try:
        claim = submit_network_claim(g.user, item_id, student_id, str(data.get("phone") or "").strip()[:20], proof)
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    from ..rls import rls_bypass
    with rls_bypass():   # the item belongs to another college
        finder = finder_note(claim.item)
    return jsonify({"status": "success", "finder": finder})


# ---------------------------------------------------------------- Phase 6: events

def _event_json(e, counts=None):
    return {"id": e.id, "slug": e.slug, "name": e.name, "campus": e.campus.name if e.campus else None,
            "starts_at": iso(e.starts_at), "ends_at": iso(e.ends_at), "is_active": e.is_active,
            "starts_on": e.starts_at.date().isoformat(), "ends_on": e.ends_at.date().isoformat(),
            "is_open": e.is_open(), "items": (counts or {}).get(e.id, 0)}


@bp.route("/events")
@college_member_required
def events():
    from ..models import Event
    rows = Event.query.filter_by(college_id=g.college.id).order_by(Event.starts_at.desc()).limit(50).all()
    counts = dict(db.session.query(Item.event_id, func.count(Item.id))
                  .filter(Item.college_id == g.college.id, Item.event_id.isnot(None), Item.status != ItemStatus.REMOVED)
                  .group_by(Item.event_id).all())
    staff = g.user.has_permission("college.settings")
    return jsonify({"items": [_event_json(e, counts) for e in rows if staff or e.is_active]})


@bp.route("/admin/events", methods=["POST"])
@college_member_required
@permission_required("college.settings")
@plan_gate("events")
def admin_create_event():
    import re
    from datetime import datetime as dt
    from ..models import Event
    f = request.get_json(silent=True) or {}
    name = str(f.get("name") or "").strip()[:160]
    if not name:
        return _err("Give the event a name.")
    try:
        starts = dt.fromisoformat(str(f.get("starts_on")))
        ends = dt.fromisoformat(str(f.get("ends_on"))).replace(hour=23, minute=59)
    except ValueError:
        return _err("Enter valid start and end dates.")
    if ends < starts:
        return _err("The event must end after it starts.")
    if (ends - starts).days > 31:
        return _err("Events can last at most 31 days.")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "event"
    base, n = slug, 2
    while Event.query.filter_by(college_id=g.college.id, slug=slug).first():
        slug, n = f"{base}-{n}", n + 1
    campus_id = f.get("campus_id") or None
    if campus_id and not Campus.query.filter_by(id=campus_id, college_id=g.college.id).first():
        return _err("Choose a valid campus.")
    event = Event(college_id=g.college.id, campus_id=campus_id, slug=slug, name=name, starts_at=starts, ends_at=ends)
    db.session.add(event)
    db.session.flush()
    audit("event.created", event, college_id=g.college.id, name=name)
    db.session.commit()
    return jsonify({"status": "success", "event": _event_json(event)})


@bp.route("/admin/events/<int:event_id>/toggle", methods=["POST"])
@college_member_required
@permission_required("college.settings")
def admin_toggle_event(event_id):
    from ..models import Event
    event = Event.query.filter_by(id=event_id, college_id=g.college.id).first_or_404()
    event.is_active = not event.is_active
    audit("event.updated", event, college_id=g.college.id, is_active=event.is_active)
    db.session.commit()
    return jsonify({"status": "success", "event": _event_json(event)})


def _qr_svg(url):
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=8, border=2, dark="#111827", light="#ffffff",
                                    xmldecl=False, svgns=True)
    resp = Response(buf.getvalue(), mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.route("/events/<int:event_id>/qr.svg")
@college_member_required
def event_qr(event_id):
    from flask import url_for
    from ..models import Event
    event = Event.query.filter_by(id=event_id, college_id=g.college.id).first_or_404()
    return _qr_svg(url_for("spa.app_shell", path=f"events/{event.id}", _external=True))


# ---------------------------------------------------------------- Phase 6: QR item tags

def _tag_json(t):
    from flask import url_for
    return {"id": t.id, "label": t.label, "code": t.code, "is_active": t.is_active, "scan_count": t.scan_count,
            "last_scanned_at": iso(t.last_scanned_at), "created_at": iso(t.created_at),
            "url": url_for("tags.scan", code=t.code, _external=True)}


@bp.route("/me/tags", methods=["GET", "POST"])
@college_member_required
def my_tags():
    import secrets
    from ..models import ItemTag
    if request.method == "POST":
        label = str((request.get_json(silent=True) or {}).get("label") or "").strip()[:80]
        if not label:
            return _err("Say what the tag is for, e.g. 'Blue water bottle'.")
        if ItemTag.query.filter_by(owner_id=g.user.id, is_active=True).count() >= 20:
            return _err("You can have up to 20 active tags.")
        tag = ItemTag(college_id=g.college.id, owner_id=g.user.id, label=label, code=secrets.token_urlsafe(9))
        db.session.add(tag)
        db.session.flush()
        audit("tag.created", tag, college_id=g.college.id)
        db.session.commit()
        return jsonify({"status": "success", "tag": _tag_json(tag)})
    tags = ItemTag.query.filter_by(owner_id=g.user.id).order_by(ItemTag.is_active.desc(), ItemTag.created_at.desc()).all()
    return jsonify({"items": [_tag_json(t) for t in tags]})


def _my_tag(tag_id):
    from ..models import ItemTag
    tag = ItemTag.query.filter_by(id=tag_id, owner_id=g.user.id).first()
    if tag is None:
        abort(404)
    return tag


@bp.route("/me/tags/<int:tag_id>/toggle", methods=["POST"])
@college_member_required
def my_tag_toggle(tag_id):
    tag = _my_tag(tag_id)
    tag.is_active = not tag.is_active
    audit("tag.updated", tag, college_id=tag.college_id, is_active=tag.is_active)
    db.session.commit()
    return jsonify({"status": "success", "tag": _tag_json(tag)})


@bp.route("/me/tags/<int:tag_id>/qr.svg")
@college_member_required
def my_tag_qr(tag_id):
    return _qr_svg(_tag_json(_my_tag(tag_id))["url"])


# ---------------------------------------------------------------- Phase 6: map

@bp.route("/map/items")
@college_member_required
@permission_required("items.view")
def map_items():
    rows = (Item.query.filter(Item.college_id == g.college.id, Item.kind == ItemKind.FOUND,
                              Item.status.in_((ItemStatus.AVAILABLE, ItemStatus.PENDING)),
                              Item.latitude.isnot(None), Item.longitude.isnot(None))
            .order_by(Item.date_found.desc()).limit(500).all())
    from ..security import CAMPUS_MODERATOR
    if g.user.role_name == CAMPUS_MODERATOR and g.user.campus_id:
        rows = [i for i in rows if i.campus_id in (None, g.user.campus_id)]
    return jsonify({"items": [{"id": i.id, "name": i.name, "category": i.category, "location": i.location,
                               "status": i.status, "lat": float(i.latitude), "lng": float(i.longitude),
                               "reported_at": iso(i.date_found)} for i in rows]})



# ---------------------------------------------------------------- Phase 7: plans (assigned by hand)

@bp.route("/platform/plans")
@permission_required("platform.manage")
def platform_plans():
    from ..services.plans import ASSIGNABLE, FEATURES, PLANS, STATUSES, current_subscription, plan_json
    colleges = College.query.order_by(College.name).all()
    out = []
    for c in colleges:
        sub = current_subscription(c)
        out.append({"id": c.id, "name": c.name, "status": c.status, "plan": plan_json(c),
                    "reference": sub.external_ref if sub else None,
                    "assigned_at": iso(sub.created_at) if sub else None})
    return jsonify({"colleges": out, "statuses": list(STATUSES), "features": FEATURES,
                    "plans": [{"key": k, "label": PLANS[k]["label"], "summary": PLANS[k]["summary"],
                               "features": sorted(PLANS[k]["features"]), "limits": PLANS[k]["limits"]} for k in ASSIGNABLE]})


@bp.route("/platform/colleges/<int:college_id>/plan", methods=["POST"])
@permission_required("platform.manage")
def platform_assign_plan(college_id):
    from datetime import datetime as dt
    from ..services.plans import PlanError, assign_plan, plan_json
    college = db.get_or_404(College, college_id)
    f = request.get_json(silent=True) or {}
    period_end = None
    if f.get("period_end"):
        try:
            period_end = dt.fromisoformat(str(f["period_end"])).replace(hour=23, minute=59, second=59)
        except ValueError:
            return _err("Enter a valid end date.")
    try:
        assign_plan(college, f.get("plan"), f.get("status", "active"), period_end, f.get("reference"), g.user)
    except PlanError as exc:
        db.session.rollback()
        return _err(str(exc))
    return jsonify({"status": "success", "plan": plan_json(college)})


# ---------------------------------------------------------------- Phase 7: browser push

@bp.route("/push/key")
@login_required
def push_key():
    from ..services.push import push_enabled
    return jsonify({"enabled": push_enabled(), "public_key": current_app.config.get("VAPID_PUBLIC_KEY") if push_enabled() else None})


@bp.route("/push/subscribe", methods=["POST"])
@login_required
def push_subscribe():
    from ..models import PushSubscription
    from ..services.push import push_enabled
    if not push_enabled():
        return _err("Push notifications aren't set up on this site.", 503)
    f = request.get_json(silent=True) or {}
    endpoint = str(f.get("endpoint") or "")
    keys = f.get("keys") or {}
    if not endpoint.startswith("https://") or len(endpoint) > 2000 or not keys.get("p256dh") or not keys.get("auth"):
        return _err("That push subscription isn't valid.")
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub is None:
        sub = PushSubscription(endpoint=endpoint, user_id=g.user.id)
        db.session.add(sub)
    sub.user_id = g.user.id          # a shared browser now belongs to whoever signed in last
    sub.p256dh, sub.auth = str(keys["p256dh"])[:200], str(keys["auth"])[:100]
    sub.user_agent = request.headers.get("User-Agent", "")[:200]
    db.session.commit()
    return jsonify({"status": "success"})


@bp.route("/push/unsubscribe", methods=["POST"])
@login_required
def push_unsubscribe():
    from ..models import PushSubscription
    endpoint = str((request.get_json(silent=True) or {}).get("endpoint") or "")
    PushSubscription.query.filter_by(endpoint=endpoint, user_id=g.user.id).delete()
    db.session.commit()
    return jsonify({"status": "success"})
