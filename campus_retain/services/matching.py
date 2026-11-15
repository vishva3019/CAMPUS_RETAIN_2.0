"""Lost/found matching, duplicate detection, smarter search and claim warnings.

Everything here is deterministic and explainable: PostgreSQL trigram similarity
(pg_trgm) on names, descriptions and places, plus category and date. No AI is needed;
the optional Claude check (services/ai.py) only adds a second opinion for staff.
"""
from datetime import timedelta

from sqlalchemy import and_, case, func, literal, or_

from ..extensions import db
from ..models import Claim, ClaimStatus, Item, ItemKind, ItemMatch, ItemStatus, MatchStatus, utcnow
from .audit import notify
from .messaging import send_email

MATCH_THRESHOLD = 0.45       # notify the lost item's owner at or above this
DUPLICATE_THRESHOLD = 0.55   # warn the reporter before posting a near-identical report
SEARCH_SIMILARITY = 0.25


def _text(*parts):
    return " ".join(p for p in parts if p).strip().lower()


def _score_expr(name, category, location, text):
    """SQL expression scoring Item rows against the given fields (0..1)."""
    name_sim = func.similarity(func.lower(Item.name), name)
    text_sim = func.word_similarity(text, func.lower(Item.name + literal(" ") + func.coalesce(Item.description, "")))
    place_sim = func.similarity(func.lower(func.coalesce(Item.location, "")), location or "")
    same_cat = case((Item.category == category, 1.0), else_=0.0) if category and category != "Other" else literal(0.0)
    return (0.5 * name_sim + 0.2 * text_sim + 0.15 * place_sim + 0.15 * same_cat), name_sim, place_sim, same_cat


def similar_items(college_id, kind, name, category=None, location=None, description=None,
                  occurred_on=None, exclude_ids=(), statuses=(ItemStatus.AVAILABLE,), min_score=0.3, limit=5,
                  campus_id=None):
    """Items of `kind` in the college that look like the given fields, best first,
    as (item, score, reasons) tuples."""
    name = (name or "").strip().lower()
    if not name:
        return []
    text = _text(name, description)
    score, name_sim, place_sim, same_cat = _score_expr(name, category, (location or "").lower(), text)
    query = (db.session.query(Item, score.label("score"), name_sim, place_sim, same_cat)
             .filter(Item.college_id == college_id, Item.kind == kind, Item.status.in_(statuses),
                     or_(func.similarity(func.lower(Item.name), name) > 0.2,
                         func.word_similarity(text, func.lower(Item.name + literal(" ") + func.coalesce(Item.description, ""))) > 0.4,
                         and_(Item.category == category, literal(bool(category and category != "Other")))))
             .filter(~Item.id.in_(list(exclude_ids) or [0])))
    if campus_id:
        query = query.filter(or_(Item.campus_id == campus_id, Item.campus_id.is_(None)))
    if occurred_on:
        # Lost after it was found (or long before) can't be the same item; allow a wide window.
        query = query.filter(or_(Item.occurred_on.is_(None),
                                 Item.occurred_on.between(occurred_on - timedelta(days=60),
                                                          occurred_on + timedelta(days=60))))
    rows = query.order_by(score.desc(), Item.date_found.desc()).limit(limit * 3).all()
    out = []
    for item, s, ns, ps, cat in rows:
        s = float(s)
        if s < min_score:
            continue
        reasons = {"name_similarity": round(float(ns), 2), "place_similarity": round(float(ps), 2),
                   "same_category": bool(cat)}
        if occurred_on and item.occurred_on:
            reasons["days_apart"] = abs((item.occurred_on - occurred_on).days)
        out.append((item, round(s, 3), reasons))
    return out[:limit]


def plausible_dates(found, lost):
    """Something can't be found before it was lost (one day of leeway for time zones and
    reporting mistakes)."""
    if found.occurred_on and lost.occurred_on:
        return found.occurred_on >= lost.occurred_on - timedelta(days=1)
    return True


def find_duplicates(college_id, kind, name, category=None, location=None, description=None, user_id=None):
    """Recent open reports of the same kind that look like this one (asked before posting)."""
    since = utcnow() - timedelta(days=14)
    found = similar_items(college_id, kind, name, category, location, description,
                          statuses=(ItemStatus.AVAILABLE, ItemStatus.PENDING), min_score=DUPLICATE_THRESHOLD, limit=3)
    return [(i, s, r) for i, s, r in found if i.date_found and i.date_found >= since]


def record_matches(item):
    """After a report: store suggested found/lost pairings and alert lost-item owners.
    Caller commits; emails are returned as callables to send after the commit."""
    opposite = ItemKind.LOST if item.kind == ItemKind.FOUND else ItemKind.FOUND
    candidates = similar_items(item.college_id, opposite, item.name, item.category, item.location,
                               item.description, item.occurred_on, exclude_ids=[item.id],
                               min_score=MATCH_THRESHOLD, limit=5, campus_id=None)
    pending_mail = []
    for other, score, reasons in candidates:
        found, lost = (item, other) if item.kind == ItemKind.FOUND else (other, item)
        if lost.reported_by_id and found.reported_by_id == lost.reported_by_id:
            continue
        if not plausible_dates(found, lost):
            continue
        exists = ItemMatch.query.filter_by(found_item_id=found.id, lost_item_id=lost.id).first()
        if exists:
            continue
        match = ItemMatch(college_id=item.college_id, found_item_id=found.id, lost_item_id=lost.id,
                          score=score, reasons=reasons)
        db.session.add(match)
        owner = lost.reported_by
        if owner is not None and item.kind == ItemKind.FOUND:
            match.notified_at = utcnow()
            notify(owner, "lost.suggested_match", f"A found item may be your {lost.name}",
                   f"'{found.name}' was reported found at {found.location}. Check it and claim it if it's yours.",
                   link=f"/app/?item={found.id}")
            pending_mail.append((owner.email, lost.name, found, owner.college))
    return [lambda m=m: send_email(m[0], f"Possible match for your {m[1]}",
                                   f"A found item that may be yours was just reported: '{m[2].name}', found at "
                                   f"{m[2].location}.\n\nSign in to Campus Retain to look at it and claim it if it's yours.",
                                   college=m[3]) for m in pending_mail]


def search_filter(query, q):
    """Typo-tolerant search: substring, trigram similarity or full-text over name,
    description, category and place. Returns (query, relevance expression)."""
    from ..blueprints.student import escape_like  # local import: avoid a cycle
    term = q.strip().lower()
    like = f"%{escape_like(term)}%"
    doc = func.to_tsvector("simple", func.coalesce(Item.name, "") + literal(" ") + func.coalesce(Item.description, "")
                           + literal(" ") + func.coalesce(Item.category, "") + literal(" ") + func.coalesce(Item.location, ""))
    tsq = func.websearch_to_tsquery("simple", term)
    relevance = func.greatest(func.similarity(func.lower(Item.name), term),
                              func.word_similarity(term, func.lower(Item.name + literal(" ") + func.coalesce(Item.description, ""))))
    query = query.filter(or_(Item.name.ilike(like, escape="\\"), Item.category.ilike(like, escape="\\"),
                             Item.location.ilike(like, escape="\\"), Item.description.ilike(like, escape="\\"),
                             doc.op("@@")(tsq),
                             func.similarity(func.lower(Item.name), term) > SEARCH_SIMILARITY,
                             func.word_similarity(term, func.lower(Item.name)) > 0.5))
    return query, relevance


def claim_flags(claim):
    """Plain-language warnings for reviewers. Rules, not AI; they never block a claim."""
    flags = []
    if claim.claimant_id:
        month = utcnow() - timedelta(days=30)
        rejected = Claim.query.filter(Claim.claimant_id == claim.claimant_id, Claim.status == ClaimStatus.REJECTED,
                                      Claim.reviewed_at >= month).count()
        if rejected >= 2:
            flags.append({"code": "recent_rejections", "message": f"{rejected} of this person's claims were rejected in the last 30 days."})
        week = utcnow() - timedelta(days=7)
        recent = Claim.query.filter(Claim.claimant_id == claim.claimant_id, Claim.timestamp >= week).count()
        if recent >= 3:
            flags.append({"code": "many_claims", "message": f"This person submitted {recent} claims in the last 7 days."})
    proof = (claim.proof_description or "").strip()
    if len(proof) < 15:
        flags.append({"code": "short_proof", "message": "The proof of ownership is very short."})
    item = claim.item
    public = _text(item.name, item.description, item.location)
    if proof and public:
        sim = db.session.query(func.similarity(proof.lower(), public)).scalar() or 0
        if sim >= 0.5:
            flags.append({"code": "copied_listing", "message": "The proof mostly repeats the public listing, not private details."})
    return flags


def confirm_matches_for(claim):
    """When a claim is approved, mark the claimant's matching lost report as confirmed."""
    if not claim.claimant_id:
        return
    matches = (ItemMatch.query.join(Item, Item.id == ItemMatch.lost_item_id)
               .filter(ItemMatch.found_item_id == claim.item_id, Item.reported_by_id == claim.claimant_id).all())
    for m in matches:
        m.status = MatchStatus.CONFIRMED
