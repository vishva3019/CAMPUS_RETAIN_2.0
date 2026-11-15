from flask import g, has_request_context, request

from ..extensions import db
from ..models import AuditLog, Notification


def audit(action, target=None, college_id=None, actor=None, **details):
    """Add an audit entry to the current transaction (caller commits)."""
    actor = actor if actor is not None else (g.get("user") if has_request_context() else None)
    if college_id is None:
        college_id = getattr(target, "college_id", None) or getattr(actor, "college_id", None)
    entry = AuditLog(
        college_id=college_id,
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else details.pop("email", None),
        action=action,
        target_type=type(target).__name__ if target is not None else None,
        target_id=getattr(target, "id", None),
        ip_address=request.remote_addr if has_request_context() else None,
        details=details or None,
    )
    db.session.add(entry)
    return entry


def notify(user, kind, title, body=None, link=None):
    """In-app notification record (shown in the notification centre, Phase 3)."""
    if user is None:
        return None
    note = Notification(user_id=user.id, college_id=user.college_id,
                        kind=kind, title=title, body=body, link=link)
    db.session.add(note)
    from .push import queue
    queue(user.id, title, body, link)
    return note
