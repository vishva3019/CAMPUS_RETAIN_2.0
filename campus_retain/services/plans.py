"""Subscription plans (Phase 7), assigned by hand by the platform admin. No payment
provider: the admin records the invoice or reference number with each change.

A college with no plan assigned is on "pilot": everything on, so colleges onboarded
before plans existed keep working until the platform admin assigns one. A plan whose
period has ended falls back to Free until it is renewed.
"""
from ..extensions import db
from ..models import Subscription, utcnow

FEATURES = {
    "analytics": "Analytics dashboard",
    "exports": "Excel, PDF and CSV exports",
    "events": "Event portals",
    "network": "Inter-college network",
    "ai": "AI photo descriptions and match checks",
}

PLANS = {
    "free": {"label": "Free", "features": set(), "limits": {"collection_points": 2},
             "summary": "Core lost & found: reports, claims, pickup codes, QR tags."},
    "standard": {"label": "Standard", "features": {"analytics", "exports", "events", "network"},
                 "limits": {"collection_points": 10},
                 "summary": "Everything in Free, plus analytics, exports, events and the college network."},
    "premium": {"label": "Premium", "features": set(FEATURES), "limits": {"collection_points": None},
                "summary": "Everything, including AI features, with no collection point limit."},
    "pilot": {"label": "Pilot (no plan assigned)", "features": set(FEATURES), "limits": {"collection_points": None},
              "summary": "Everything on until the platform admin assigns a plan."},
}
ASSIGNABLE = ("free", "standard", "premium")
STATUSES = ("trialing", "active", "cancelled")


class PlanError(ValueError):
    pass


def current_subscription(college):
    return (Subscription.query.filter_by(college_id=college.id)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc()).first())


def effective_plan(college):
    """(plan key, subscription or None, note) for a college right now."""
    sub = current_subscription(college)
    if sub is None:
        return "pilot", None, None
    if sub.status == "cancelled":
        return "free", sub, "The plan was cancelled."
    if sub.current_period_end and sub.current_period_end < utcnow():
        return "free", sub, f"The {PLANS.get(sub.plan, {}).get('label', sub.plan)} plan ended on {sub.current_period_end:%d %b %Y}."
    return (sub.plan if sub.plan in PLANS else "free"), sub, None


def feature_allowed(college, feature):
    return feature in PLANS[effective_plan(college)[0]]["features"]


def limit_for(college, name):
    return PLANS[effective_plan(college)[0]]["limits"].get(name)


def plan_json(college):
    key, sub, note = effective_plan(college)
    plan = PLANS[key]
    return {"key": key, "label": plan["label"], "features": sorted(plan["features"]), "limits": plan["limits"],
            "note": note,
            "period_end": sub.current_period_end.isoformat() + "Z" if sub and sub.current_period_end else None,
            "status": sub.status if sub else None}


def assign_plan(college, plan, status, period_end, reference, actor):
    """Record a plan change (a new Subscription row; history is kept). Commits."""
    from .audit import audit
    if plan not in ASSIGNABLE:
        raise PlanError("Choose Free, Standard or Premium.")
    if status not in STATUSES:
        raise PlanError("Choose a valid status.")
    now = utcnow()
    if period_end is not None and period_end < now and status != "cancelled":
        raise PlanError("The end date is in the past.")
    sub = Subscription(college_id=college.id, plan=plan, status=status, current_period_start=now,
                       current_period_end=period_end, external_ref=(reference or "").strip()[:120] or None)
    db.session.add(sub)
    db.session.flush()
    audit("plan.assigned", sub, college_id=college.id, actor=actor, plan=plan, status=status,
          period_end=period_end.date().isoformat() if period_end else None, reference=sub.external_ref)
    db.session.commit()
    return sub


def plan_gate(feature):
    """View decorator: 403 with a clear message when the college's plan lacks a feature."""
    from functools import wraps

    from flask import g, jsonify

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            college = g.get("college")
            if college is not None and not feature_allowed(college, feature):
                return jsonify({"error": f"{FEATURES[feature]} isn't included in your college's plan. "
                                         "Ask the Campus Retain team to upgrade it.", "plan_required": feature}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator
