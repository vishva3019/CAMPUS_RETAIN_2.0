"""JSON shapes for the React frontend. Private fields (secret details, claimant contact
details) are only included when the viewer's permissions allow it."""
from flask import current_app, g

from .blueprints.media import photo_urls
from .models import ClaimStatus, ItemKind, ItemStatus
from .services.claims import pickup_instructions


def iso(dt):
    return dt.isoformat() + "Z" if dt is not None else None


def day(d):
    return d.isoformat() if d is not None else None


def point_json(p, held=None):
    if p is None:
        return None
    out = {"id": p.id, "name": p.name, "opening_hours": p.opening_hours, "description": p.description,
           "campus": p.campus.name if p.campus else None, "is_active": p.is_active,
           "pickup_text": p.pickup_text()}
    if held is not None:
        out["items_held"] = held.get(p.id, 0)
    return out


def match_json(m, side):
    """side: the item to show ('found' when shown to a lost-item owner, else 'lost')."""
    other = m.found_item if side == "found" else m.lost_item
    return {"id": m.id, "score": round(m.score, 2), "reasons": m.reasons or {}, "status": m.status,
            "ai_verdict": m.ai_verdict, "ai_reason": m.ai_reason, "ai_checked_at": iso(m.ai_checked_at),
            "item": item_json(other)}


def item_ref(item):
    """Short reference shown to students, e.g. F-00123 (found) or L-00045 (lost)."""
    return f"{'F' if item.kind == ItemKind.FOUND else 'L'}-{item.id:05d}"


CLAIM_STAGES = {
    # status -> (stage key, label shown to the student)
    ClaimStatus.PENDING: ("under_review", "Under review"),
    ClaimStatus.APPROVED: ("awaiting_pickup", "Approved: awaiting pickup"),
    ClaimStatus.COLLECTED: ("returned", "Returned to you"),
    ClaimStatus.REJECTED: ("rejected", "Not approved"),
    ClaimStatus.WITHDRAWN: ("withdrawn", "Withdrawn"),
    ClaimStatus.CLOSED: ("closed", "Closed"),
}


def item_json(item, staff=False):
    user = g.user
    mine = item.reported_by_id == user.id
    out = {
        "id": item.id, "ref": item_ref(item), "kind": item.kind, "name": item.name, "category": item.category,
        "location": item.location, "description": item.description,
        "occurred_on": day(item.occurred_on), "reported_at": iso(item.date_found),
        "status": item.status, "photos": photo_urls(item), "is_mine": mine,
        "campus": item.campus.name if item.campus else None,
        "collection_point": point_json(item.collection_point),
        "event": {"id": item.event.id, "name": item.event.name} if item.event else None,
        "has_location": item.latitude is not None,
        "can_claim": (item.kind == ItemKind.FOUND and item.status == ItemStatus.AVAILABLE and not mine
                      and user.has_permission("claims.submit")),
        "can_report_found": (item.kind == ItemKind.LOST and item.status == ItemStatus.AVAILABLE and not mine
                             and user.has_permission("items.report")),
    }
    if staff:
        out["reported_by"] = item.reported_by.email if item.reported_by else None
        out["removed_at"] = iso(item.removed_at)
        if user.has_permission("claims.review"):
            from .services.matching import claim_flags
            out["secret_detail"] = item.secret_detail
            out["claims"] = [staff_claim_json(c) for c in reversed(item.claims)]
            for c, data in zip(reversed(item.claims), out["claims"]):
                if c.status == ClaimStatus.PENDING:
                    data["flags"] = claim_flags(c)
        else:
            out["claims"] = [{"id": c.id, "status": c.status, "timestamp": iso(c.timestamp)}
                             for c in reversed(item.claims)]
    return out


def finder_note(item, contact=False):
    """Who reported a found item, shown to the claimant on the "paper plane" note.
    On a new claim it is deliberately limited: first name + last initial, role and
    department, and where/when it was found. Only once staff have approved the claim
    (contact=True) does the owner also get the finder's full name, email and phone,
    so they can thank them. Finders are told this when they report."""
    u = item.reported_by
    name, role, dept = None, None, None
    if u is not None:
        parts = (u.full_name or "").split()
        if parts:
            name = parts[0] + (f" {parts[-1][0].upper()}." if len(parts) > 1 else "")
        if u.student_id:
            role, dept = "Student", (u.department_name or None)
        elif u.role_name:
            role = u.role_name.replace("_", " ").title()
    if contact and u is not None and (u.full_name or "").strip():
        name = u.full_name.strip()
    out = {
        "name": name or ("A fellow student" if role == "Student" else "Campus staff" if role else "Someone on campus"),
        "role": role, "department": dept,
        "found_at": item.location, "found_on": day(item.occurred_on), "reported_at": iso(item.date_found),
        "ref": item_ref(item),
        "pickup": item.collection_point.name if item.collection_point else None,
        "college": item.college.name if item.college else None,
        "email": None, "phone": None,
    }
    if contact and u is not None:
        out["email"], out["phone"] = u.email, (u.phone or None)
    return out


def staff_claim_json(c):
    other = (c.claimant.college if c.claimant is not None and c.claimant.college_id != c.college_id else None)
    return {
        "claimant_college": other.name if other else None,
        "id": c.id, "status": c.status, "timestamp": iso(c.timestamp),
        "student_id": c.student_id, "student_email": c.student_email, "phone": c.phone,
        "proof_description": c.proof_description,
        "reviewed_by": c.reviewed_by.email if c.reviewed_by else None,
        "reviewed_at": iso(c.reviewed_at), "review_remarks": c.review_remarks,
        "collected_at": iso(c.collected_at),
        "collected_by": c.collected_by.email if c.collected_by else None,
    }


def my_claim_json(c, college):
    item = c.item
    stage, stage_label = CLAIM_STAGES.get(c.status, (c.status, c.status.title()))
    out = {
        "id": c.id, "status": c.status, "stage": stage, "stage_label": stage_label,
        "timestamp": iso(c.timestamp), "reviewed_at": iso(c.reviewed_at),
        "review_remarks": c.review_remarks if c.status in (ClaimStatus.APPROVED, ClaimStatus.REJECTED) else None,
        "collected_at": iso(c.collected_at),
        "item": {"id": item.id, "ref": item_ref(item), "name": item.name, "category": item.category,
                 "location": item.location,
                 "photo": (photo_urls(item) or [None])[0] if item.college_id == g.user.college_id else None,
                 "college": item.college.name if item.college_id != g.user.college_id else None},
        "pickup": None,
        # The finder's contact details are shared with the owner only after approval.
        "finder": (finder_note(item, contact=True)
                   if c.status in (ClaimStatus.APPROVED, ClaimStatus.COLLECTED) else None),
    }
    if c.status == ClaimStatus.APPROVED:
        out["pickup"] = {
            "instructions": pickup_instructions(item, college),
            "point": point_json(item.collection_point),
            "code_sent_at": iso(c.pickup_code_sent_at),
            "code_expires_at": iso(c.pickup_code_expires_at),
            "locked": c.pickup_code_attempts >= current_app.config["PICKUP_CODE_MAX_ATTEMPTS"],
        }
    return out


def desk_claim_json(c):
    item = c.item
    return {
        "id": c.id, "student_email": c.student_email, "student_id": c.student_id, "phone": c.phone,
        "reviewed_at": iso(c.reviewed_at), "wrong_attempts": c.pickup_code_attempts,
        "has_code": bool(c.pickup_code_hash),
        "collected_at": iso(c.collected_at),
        "collected_by": c.collected_by.email if c.collected_by else None,
        "item": {"id": item.id, "name": item.name, "photo": (photo_urls(item) or [None])[0],
                 "collection_point": item.collection_point.name if item.collection_point else None},
    }


# Links stored by older notifications point at the classic pages; send them to the app.
_LEGACY_LINKS = (("/me", "/app/activity"), ("/dashboard?q=", "/app/?q="), ("/dashboard", "/app/"))


def notification_json(n):
    link = n.link if n.link and n.link.startswith("/") and not n.link.startswith("//") else None
    if link and not link.startswith("/app"):
        for old, new in _LEGACY_LINKS:
            if link == old or (old.endswith("=") and link.startswith(old)):
                link = new + link[len(old):]
                break
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": link,
            "created_at": iso(n.created_at), "read": n.read_at is not None}


def page_json(pagination, items):
    return {"items": items, "page": pagination.page, "pages": pagination.pages,
            "total": pagination.total, "per_page": pagination.per_page}
