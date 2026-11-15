"""College analytics computed from real rows (no estimates, no sample data).

Definitions (shown to admins next to each number):

- found / lost reported: items reported in the period (removed listings excluded).
- recovered: found items reported in the period that now have an approved or collected
  claim (status Claimed or Returned).
- recovery rate: recovered / found reported.
- time to return: from the report to the confirmed pickup, for pickups in the period.
- returned: pickups confirmed at the desk in the period.
"""
from datetime import date, datetime, timedelta
from statistics import median

from sqlalchemy import func

from ..extensions import db
from ..models import Campus, Claim, ClaimStatus, CollectionPoint, Item, ItemKind, ItemStatus, utcnow
from ..security import tenant_query


def parse_period(args):
    """(start, end) as naive UTC datetimes; default: the last 12 full months plus this one."""
    today = utcnow().date()
    try:
        end_day = date.fromisoformat(args["to"]) if args.get("to") else today
    except ValueError:
        raise ValueError("Enter a valid end date.")
    try:
        start_day = (date.fromisoformat(args["from"]) if args.get("from")
                     else date(today.year - 1, today.month, 1))
    except ValueError:
        raise ValueError("Enter a valid start date.")
    if start_day > end_day:
        raise ValueError("The start date must be before the end date.")
    if (end_day - start_day).days > 366 * 3:
        raise ValueError("Choose a period of 3 years or less.")
    return datetime.combine(start_day, datetime.min.time()), datetime.combine(end_day + timedelta(days=1), datetime.min.time())


def _months(start, end):
    months, cur = [], date(start.year, start.month, 1)
    while cur < end.date():
        months.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return months


def _items(start, end, kind):
    return tenant_query(Item).filter(Item.kind == kind, Item.status != ItemStatus.REMOVED,
                                     Item.date_found >= start, Item.date_found < end)


def college_analytics(start, end):
    found_q = _items(start, end, ItemKind.FOUND)
    found = found_q.count()
    lost = _items(start, end, ItemKind.LOST).count()
    recovered = found_q.filter(Item.status.in_((ItemStatus.CLAIMED, ItemStatus.RETURNED))).count()
    lost_closed = _items(start, end, ItemKind.LOST).filter(Item.status == ItemStatus.RETURNED).count()

    claims_q = (tenant_query(Claim).join(Item, Item.id == Claim.item_id)
                .filter(Claim.timestamp >= start, Claim.timestamp < end))
    if g_campus := _campus_filter():
        claims_q = claims_q.filter(Item.campus_id == g_campus)
    outcomes = dict(claims_q.with_entities(Claim.status, func.count(Claim.id)).group_by(Claim.status).all())

    pickups_q = (tenant_query(Claim).join(Item, Item.id == Claim.item_id)
                 .filter(Claim.status == ClaimStatus.COLLECTED,
                         Claim.collected_at >= start, Claim.collected_at < end))
    if g_campus:
        pickups_q = pickups_q.filter(Item.campus_id == g_campus)
    pickups = pickups_q.with_entities(Claim.collected_at, Item.date_found).all()
    days = [(c - f).total_seconds() / 86400 for c, f in pickups if c and f and c >= f]

    month = func.date_trunc("month", Item.date_found)
    found_by_month = dict(found_q.with_entities(month, func.count(Item.id)).group_by(month).all())
    lost_by_month = dict(_items(start, end, ItemKind.LOST).with_entities(month, func.count(Item.id)).group_by(month).all())
    pmonth = func.date_trunc("month", Claim.collected_at)
    returned_by_month = dict(pickups_q.with_entities(pmonth, func.count(Claim.id)).group_by(pmonth).all())

    def key(m):
        return datetime(m.year, m.month, 1)

    monthly = [{"month": m.isoformat()[:7],
                "found": found_by_month.get(key(m), 0),
                "lost": lost_by_month.get(key(m), 0),
                "returned": returned_by_month.get(key(m), 0)} for m in _months(start, end)]

    recovered_case = func.sum(db.case((Item.status.in_((ItemStatus.CLAIMED, ItemStatus.RETURNED)), 1), else_=0))
    by_category = [{"category": c or "Other", "found": n, "recovered": int(r or 0)} for c, n, r in
                   found_q.with_entities(Item.category, func.count(Item.id), recovered_case)
                   .group_by(Item.category).order_by(func.count(Item.id).desc()).all()]
    by_campus = [{"campus": name or "Not set", "found": n, "recovered": int(r or 0)} for name, n, r in
                 found_q.outerjoin(Campus, Campus.id == Item.campus_id)
                 .with_entities(Campus.name, func.count(Item.id), recovered_case)
                 .group_by(Campus.name).order_by(func.count(Item.id).desc()).all()]
    by_point = [{"collection_point": name or "Not handed in", "found": n} for name, n in
                found_q.outerjoin(CollectionPoint, CollectionPoint.id == Item.collection_point_id)
                .with_entities(CollectionPoint.name, func.count(Item.id))
                .group_by(CollectionPoint.name).order_by(func.count(Item.id).desc()).all()]

    now = utcnow()
    oldest_pending = (tenant_query(Claim).filter(Claim.status == ClaimStatus.PENDING)
                      .with_entities(func.min(Claim.timestamp)).scalar())
    oldest_pickup = (tenant_query(Claim).filter(Claim.status == ClaimStatus.APPROVED)
                     .with_entities(func.min(Claim.reviewed_at)).scalar())
    return {
        "period": {"from": start.date().isoformat(), "to": (end - timedelta(days=1)).date().isoformat()},
        "totals": {
            "found_reported": found, "lost_reported": lost, "recovered": recovered,
            "recovery_rate": round(recovered / found, 4) if found else None,
            "returned": len(pickups), "lost_closed_found": lost_closed,
            "claims_submitted": sum(outcomes.values()),
            "avg_days_to_return": round(sum(days) / len(days), 1) if days else None,
            "median_days_to_return": round(median(days), 1) if days else None,
        },
        "claim_outcomes": {s: outcomes.get(s, 0) for s in
                           (ClaimStatus.PENDING, ClaimStatus.APPROVED, ClaimStatus.COLLECTED,
                            ClaimStatus.REJECTED, ClaimStatus.WITHDRAWN, ClaimStatus.CLOSED)},
        "backlog": {
            "pending_claims": tenant_query(Claim).filter(Claim.status == ClaimStatus.PENDING).count(),
            "oldest_pending_days": (now - oldest_pending).days if oldest_pending else None,
            "awaiting_pickup": tenant_query(Claim).filter(Claim.status == ClaimStatus.APPROVED).count(),
            "oldest_pickup_days": (now - oldest_pickup).days if oldest_pickup else None,
            "unclaimed_over_30_days": tenant_query(Item).filter(
                Item.kind == ItemKind.FOUND, Item.status == ItemStatus.AVAILABLE,
                Item.date_found < now - timedelta(days=30)).count(),
        },
        "monthly": monthly,
        "by_category": by_category,
        "by_campus": by_campus,
        "by_collection_point": by_point,
    }


def _campus_filter():
    """Campus moderators only see their campus (tenant_query already applies this to Item)."""
    from flask import g

    from ..security import CAMPUS_MODERATOR
    user = g.get("user")
    if user is not None and user.role_name == CAMPUS_MODERATOR and user.campus_id:
        return user.campus_id
    return None
