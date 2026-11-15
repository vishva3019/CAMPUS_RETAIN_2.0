"""Inter-college network (Phase 6).

Colleges opt in (College.inter_college_matching). Students of an opted-in college can
search found items at other opted-in colleges. Listings are redacted: name, category,
date, college and city only - no photos, places, descriptions or reporter details.
A claim made through the network belongs to the item's college: its staff review it and
hand the item over at their own pickup desk with the usual pickup code.
"""
from ..extensions import db
from ..models import College, CollegeStatus, Item, ItemKind, ItemStatus
from .audit import audit
from .claims import ClaimError, submit_claim


def network_open(college):
    from .plans import feature_allowed
    return bool(college and college.status == CollegeStatus.ACTIVE and college.inter_college_matching
                and feature_allowed(college, "network"))


def network_query(user_college):
    """Open found items at the *other* opted-in, active colleges whose plan includes the network."""
    ids = [c.id for c in opted_in_colleges(user_college.id)] or [0]
    return Item.query.filter(Item.college_id.in_(ids), Item.kind == ItemKind.FOUND,
                             Item.status == ItemStatus.AVAILABLE)


def network_search(user_college, q=None, category=None):
    query = network_query(user_college)
    if q:
        from .matching import search_filter
        query, relevance = search_filter(query, q)
        query = query.order_by(relevance.desc(), Item.date_found.desc())
    else:
        query = query.order_by(Item.date_found.desc(), Item.id.desc())
    if category:
        query = query.filter(Item.category == category)
    return query


def network_item_json(item):
    """Redacted listing for students of other colleges."""
    return {"id": item.id, "name": item.name, "category": item.category,
            "occurred_on": item.occurred_on.isoformat() if item.occurred_on else None,
            "reported_at": item.date_found.isoformat() + "Z" if item.date_found else None,
            "college": item.college.name, "city": item.college.city}


def submit_network_claim(user, item_id, student_id, phone, proof):
    from ..rls import rls_bypass
    with rls_bypass():
        return _submit_network_claim(user, item_id, student_id, phone, proof)


def _submit_network_claim(user, item_id, student_id, phone, proof):
    if not network_open(user.college):
        raise ClaimError("Your college hasn't joined the inter-college network.", 403)
    item = (network_query(user.college).filter(Item.id == item_id).with_for_update(of=Item).first())
    if item is None:
        raise ClaimError("Item not found.", 404)
    claim = submit_claim(user, item.id, student_id, phone, proof, item=item)
    audit("network.claim", claim, college_id=item.college_id, claimant_college_id=user.college_id)
    db.session.commit()
    return claim


def opted_in_colleges(exclude_id):
    from .plans import feature_allowed
    rows = (College.query.filter(College.inter_college_matching.is_(True), College.status == CollegeStatus.ACTIVE,
                                 College.id != exclude_id).order_by(College.name).all())
    return [c for c in rows if feature_allowed(c, "network")]

