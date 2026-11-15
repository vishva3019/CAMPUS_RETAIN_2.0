from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Campus, Claim, CollectionPoint, Item, ItemKind, ItemStatus
from ..security import college_member_required, permission_required, tenant_query
from ..services.audit import audit

bp = Blueprint("admin", __name__)

STATUS_FILTERS = {
    "": ItemStatus.VISIBLE,
    "available": (ItemStatus.AVAILABLE,),
    "pending": (ItemStatus.PENDING,),
    "claimed": (ItemStatus.CLAIMED,),
    "returned": (ItemStatus.RETURNED,),
    "removed": (ItemStatus.REMOVED,),
}


STAFF_PERMISSIONS = ("claims.review", "items.manage", "collection.verify")


def admin_items_query(args):
    """Filtered staff item list shared by the admin page, the JSON API and CSV export."""
    status_key = args.get("status", "")
    if status_key not in STATUS_FILTERS:
        status_key = ""
    kind = args.get("kind", ItemKind.FOUND)
    if kind not in (ItemKind.FOUND, ItemKind.LOST):
        kind = ItemKind.FOUND
    query = (tenant_query(Item).filter(Item.status.in_(STATUS_FILTERS[status_key]), Item.kind == kind)
             .options(selectinload(Item.claims).joinedload(Claim.reviewed_by),
                      selectinload(Item.claims).joinedload(Claim.collected_by),
                      selectinload(Item.images), selectinload(Item.reported_by)))
    q = args.get("q", "").strip()[:100]
    relevance = None
    if q:
        from ..services.matching import search_filter
        query, relevance = search_filter(query, q)
    category = args.get("category", "").strip()
    if category:
        query = query.filter(Item.category == category)
    try:
        campus_id = int(args.get("campus") or 0)
    except (TypeError, ValueError):
        campus_id = 0
    if campus_id:
        query = query.filter(Item.campus_id == campus_id)
    order = ([relevance.desc()] if relevance is not None else []) + [Item.date_found.desc(), Item.id.desc()]
    return query.order_by(*order), q, status_key, kind


def admin_counts():
    counts = {s: tenant_query(Item).filter(Item.status == s, Item.kind == ItemKind.FOUND).count()
              for s in (ItemStatus.AVAILABLE, ItemStatus.PENDING, ItemStatus.CLAIMED)}
    counts["lost"] = tenant_query(Item).filter(Item.kind == ItemKind.LOST,
                                               Item.status == ItemStatus.AVAILABLE).count()
    return counts


def create_collection_point(college, form, actor=None):
    """Raises ValueError with a user-facing message. Commits."""
    name = (form.get("name") or "").strip()[:120]
    try:
        campus_id = int(form.get("campus_id")) if form.get("campus_id") not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("Choose a valid campus.")
    if not name:
        raise ValueError("Give the collection point a name.")
    if campus_id and not Campus.query.filter_by(id=campus_id, college_id=college.id, is_active=True).first():
        raise ValueError("Choose a valid campus.")
    if CollectionPoint.query.filter(CollectionPoint.college_id == college.id,
                                    db.func.lower(CollectionPoint.name) == name.lower()).first():
        raise ValueError("A collection point with that name already exists.")
    from ..services.plans import limit_for
    cap = limit_for(college, "collection_points")
    if cap is not None and CollectionPoint.query.filter_by(college_id=college.id, is_active=True).count() >= cap:
        raise ValueError(f"Your college's plan allows {cap} open collection points. Close one or ask for an upgrade.")
    point = CollectionPoint(
        college_id=college.id, campus_id=campus_id, name=name,
        description=(form.get("description") or "").strip()[:1000] or None,
        opening_hours=(form.get("opening_hours") or "").strip()[:160] or None)
    db.session.add(point)
    db.session.flush()
    audit("collection_point.created", point, actor=actor, name=name)
    db.session.commit()
    return point


def toggle_point(college, point_id, actor=None):
    point = CollectionPoint.query.filter_by(id=point_id, college_id=college.id).first_or_404()
    point.is_active = not point.is_active
    audit("collection_point.updated", point, actor=actor, is_active=point.is_active)
    db.session.commit()
    return point


def points_held(college):
    return dict(db.session.query(Item.collection_point_id, db.func.count(Item.id))
                .filter(Item.college_id == college.id,
                        Item.status.in_((ItemStatus.AVAILABLE, ItemStatus.PENDING, ItemStatus.CLAIMED)),
                        Item.collection_point_id.isnot(None))
                .group_by(Item.collection_point_id).all())


@bp.route("/admin")
@college_member_required
def dashboard():
    user = g.user
    if not any(user.has_permission(p) for p in STAFF_PERMISSIONS):
        abort(403)

    query, q, status_key, kind = admin_items_query(request.args)

    page = query.paginate(page=request.args.get("page", 1, type=int),
                          per_page=current_app.config["PAGE_SIZE"], error_out=False)
    counts = admin_counts()
    points = (tenant_query(CollectionPoint).filter_by(is_active=True)
              .order_by(CollectionPoint.name).all())
    return render_template(
        "admin.html", items=page.items, pagination=page, q=q, status_key=status_key,
        kind=kind, counts=counts, college=g.college, points=points,
        can_verify=user.has_permission("collection.verify"),
        can_settings=user.has_permission("college.settings"),
        can_review=user.has_permission("claims.review"),
        can_manage=user.has_permission("items.manage"),
        can_view_secret=user.has_permission("claims.review"),
    )


# ---------------------------------------------------------------- collection points

@bp.route("/admin/collection-points", methods=["GET", "POST"])
@college_member_required
@permission_required("college.settings")
def collection_points():
    college = g.college
    campuses = Campus.query.filter_by(college_id=college.id, is_active=True).order_by(Campus.name).all()
    if request.method == "POST":
        try:
            point = create_collection_point(college, request.form, actor=g.user)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
        else:
            flash(f"Added {point.name}.", "success")
        return redirect(url_for("admin.collection_points"))

    points = (CollectionPoint.query.filter_by(college_id=college.id)
              .order_by(CollectionPoint.is_active.desc(), CollectionPoint.name).all())
    held = points_held(college)
    return render_template("collection_points.html", points=points, campuses=campuses,
                           held=held, college=college)


@bp.route("/admin/collection-points/<int:point_id>/toggle", methods=["POST"])
@college_member_required
@permission_required("college.settings")
def toggle_collection_point(point_id):
    point = toggle_point(g.college, point_id, actor=g.user)
    flash(f"{point.name} is now {'open' if point.is_active else 'closed'} for new items.", "success")
    return redirect(url_for("admin.collection_points"))
