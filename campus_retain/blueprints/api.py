"""JSON endpoints used by the pages. Paths are unchanged from 2.0."""
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request, url_for

from ..extensions import db
from ..models import Campus, CollectionPoint, Item, ItemKind, ItemStatus, utcnow
from ..security import college_member_required, get_tenant_object, permission_required, tenant_query
from ..services.audit import audit, notify
from ..services.claims import ClaimError, approve_claim, reject_claim, submit_claim
from ..services.images import ImageError, delete_objects, store_item_photos
from ..services.messaging import send_email
from ..serializers import finder_note

bp = Blueprint("api", __name__, url_prefix="/api")

CATEGORIES = ("Electronics", "Accessories", "Books", "Clothing", "ID & Cards",
              "Keys", "Bags", "Bottles", "Sports", "Other")


def _err(message, status=400):
    return jsonify({"error": message}), status


def _text(source, key, limit, required=False):
    value = str(source.get(key, "") or "").strip()
    if required and not value:
        raise ValueError(key)
    return value[:limit]


def _collection_point(point_id):
    if not point_id:
        return None
    point = (CollectionPoint.query.filter_by(id=point_id, college_id=g.user.college_id, is_active=True)
             .first())
    if point is None:
        raise ValueError("Choose a valid collection point.")
    return point


@bp.route("/report", methods=["POST"])
@college_member_required
@permission_required("items.report")
def report_item():
    """Report a found item (kind=found, default) or a lost one (kind=lost)."""
    form = request.form
    kind = form.get("kind", ItemKind.FOUND)
    if kind not in (ItemKind.FOUND, ItemKind.LOST):
        return _err("Unknown report type.")
    try:
        name = _text(form, "name", 120, required=True)
        location = _text(form, "location", 150, required=True)
    except ValueError:
        return _err("Item name and location are required.")

    category = _text(form, "category", 50) or "Other"
    if category not in CATEGORIES:
        category = "Other"

    occurred_on = None
    if form.get("occurred_on"):
        try:
            occurred_on = date.fromisoformat(form["occurred_on"])
        except ValueError:
            return _err("Enter a valid date.")
        # One day of leeway: "today" in India (UTC+5:30) can be tomorrow's date in UTC terms.
        if occurred_on > utcnow().date() + timedelta(days=1):
            return _err("The date can't be in the future.")

    campus_id = form.get("campus_id", type=int) or g.user.campus_id
    if campus_id and not Campus.query.filter_by(id=campus_id, college_id=g.user.college_id).first():
        return _err("Choose a valid campus.")

    event = None
    if form.get("event_id"):
        from ..models import Event
        event = Event.query.filter_by(id=form.get("event_id", type=int), college_id=g.user.college_id).first()
        if event is None or not event.is_open():
            return _err("That event isn't taking reports.")
    latitude = longitude = None
    if form.get("latitude") or form.get("longitude"):
        try:
            latitude, longitude = float(form["latitude"]), float(form["longitude"])
        except (KeyError, ValueError):
            return _err("The location couldn't be read.")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return _err("The location couldn't be read.")
        # Store only an approximate place (~100 m) - never an exact position.
        latitude, longitude = round(latitude, 3), round(longitude, 3)

    point, lost_match = None, None
    if kind == ItemKind.FOUND:
        try:
            point = _collection_point(form.get("collection_point_id", type=int))
        except ValueError as exc:
            return _err(str(exc))
        lost_id = form.get("lost_item_id", type=int)
        if lost_id:
            lost_match = tenant_query(Item).filter(
                Item.id == lost_id, Item.kind == ItemKind.LOST,
                Item.status == ItemStatus.AVAILABLE).first()
            if lost_match is None:
                return _err("That lost-item report is no longer open.", 404)
            if lost_match.reported_by_id == g.user.id:
                return _err("That's your own lost-item report.", 409)

    item = Item(
        college_id=g.user.college_id, campus_id=campus_id, reported_by_id=g.user.id,
        kind=kind, name=name, category=category, location=location,
        description=_text(form, "description", 2000) or None,
        # Lost reports have no private detail: the owner proves ownership when claiming.
        secret_detail=(_text(form, "secret_detail", 2000) or None) if kind == ItemKind.FOUND else None,
        collection_point_id=point.id if point else None,
        event_id=event.id if event else None, latitude=latitude, longitude=longitude,
        occurred_on=occurred_on, status=ItemStatus.AVAILABLE, date_found=utcnow(),
    )
    db.session.add(item)

    files = request.files.getlist("images") + request.files.getlist("image")
    try:
        written = store_item_photos(item, files)
    except ImageError as exc:
        db.session.rollback()
        return _err(str(exc))

    try:
        db.session.flush()
        audit("item.reported", item, kind=kind, photos=len(written),
              lost_item_id=lost_match.id if lost_match else None)
        from ..services.matching import record_matches
        match_mail = record_matches(item)
        if lost_match is not None and lost_match.reported_by is not None:
            notify(lost_match.reported_by, "lost.possible_match",
                   f"Someone may have found your {lost_match.name}",
                   f"'{item.name}' was reported found at {item.location}. Check it and claim it if it's yours.",
                   link=url_for("student.dashboard", q=item.name))
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_objects(written)
        raise

    for send in match_mail:
        send()
    if lost_match is not None and lost_match.reported_by is not None:
        send_email(lost_match.reported_by.email, f"Possible match for your {lost_match.name}",
                   f"Someone at {g.college.display_name} reported a found item that may be yours: "
                   f"'{item.name}', found at {item.location}.\n\nSign in to Campus Retain, look at the "
                   "item and submit a claim if it's yours.", college=g.college)
    if kind == ItemKind.FOUND and g.college.contact_email:
        send_email(g.college.contact_email, f"New found item: {item.name}",
                   f"'{item.name}' was reported found at {item.location}"
                   + (f" and handed to {point.name}" if point else "") + ".", college=g.college)
    from ..serializers import item_json, item_ref
    suggestions = []
    if kind == ItemKind.LOST:
        # "Is it one of these?" Found items already reported that look like this lost one.
        from ..services.matching import MATCH_THRESHOLD, plausible_dates, similar_items
        rows = similar_items(item.college_id, ItemKind.FOUND, item.name, item.category, item.location,
                             item.description, item.occurred_on, exclude_ids=[item.id],
                             min_score=MATCH_THRESHOLD - 0.1, limit=4)
        suggestions = [dict(item_json(f), score=sc) for f, sc, _r in rows if plausible_dates(f, item)]
    return jsonify({"status": "success", "id": item.id, "ref": item_ref(item),
                    "owners_alerted": len(match_mail), "suggestions": suggestions})


@bp.route("/item/<int:item_id>/collection-point", methods=["POST"])
@college_member_required
@permission_required("items.manage")
def set_collection_point(item_id):
    item = get_tenant_object(Item, item_id)
    if item.kind != ItemKind.FOUND or item.status in (ItemStatus.RETURNED, ItemStatus.REMOVED):
        return _err("Only found items that haven't been returned can be moved.", 409)
    data = request.get_json(silent=True) or {}
    raw = data.get("collection_point_id")
    try:
        point = _collection_point(int(raw) if raw not in (None, "") else None)
    except (ValueError, TypeError):
        return _err("Choose a valid collection point.")
    item.collection_point_id = point.id if point else None
    audit("item.collection_point", item, collection_point_id=item.collection_point_id)
    db.session.commit()
    return jsonify({"status": "success"})


@bp.route("/claim", methods=["POST"])
@college_member_required
@permission_required("claims.submit")
def claim_item():
    data = request.get_json(silent=True) or {}
    try:
        student_id = _text(data, "student_id", 50, required=True)
        proof = _text(data, "proof_description", 2000, required=True)
    except ValueError:
        return _err("Student ID and proof of ownership are required.")
    phone = _text(data, "phone", 20)
    try:
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError):
        return _err("Invalid item.")
    # Any email in the body is ignored: the claimant is always the logged-in user.
    try:
        claim = submit_claim(g.user, item_id, student_id, phone, proof)
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    return jsonify({"status": "success", "finder": finder_note(claim.item)})


@bp.route("/admin/approve/<int:item_id>", methods=["POST"])
@college_member_required
@permission_required("claims.review")
def approve(item_id):
    data = request.get_json(silent=True) or {}
    try:
        approve_claim(g.user, item_id, _text(data, "remarks", 1000))
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    return jsonify({"status": "success"})


@bp.route("/admin/reject/<int:item_id>", methods=["POST"])
@college_member_required
@permission_required("claims.review")
def reject(item_id):
    data = request.get_json(silent=True) or {}
    try:
        reject_claim(g.user, item_id, _text(data, "remarks", 1000))
    except ClaimError as exc:
        return _err(str(exc), exc.status)
    return jsonify({"status": "success"})


@bp.route("/item/delete/<int:item_id>", methods=["POST"])
@college_member_required
@permission_required("items.manage")
def remove_item(item_id):
    """Removes a listing from view. The row and its claim history are kept (audit)."""
    item = get_tenant_object(Item, item_id)
    if item.status == ItemStatus.REMOVED:
        return _err("This item is already removed.", 409)
    if item.status == ItemStatus.PENDING:
        return _err("Approve or reject the pending claim before removing this item.", 409)
    item.status = ItemStatus.REMOVED
    item.removed_at, item.removed_by_id = utcnow(), g.user.id
    audit("item.removed", item)
    db.session.commit()
    return jsonify({"status": "success"})
