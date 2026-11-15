"""Browser push notifications (Web Push with VAPID keys). Phase 7.

Every in-app notification is also pushed to the user's subscribed browsers after the
transaction commits. Push services are told nothing but the title, body and link.
Dead subscriptions (404/410 from the push service) are removed.
"""
import json

from flask import current_app, g, has_app_context, has_request_context
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..extensions import db
from ..models import PushSubscription, utcnow

PENDING_KEY = "pending_push"


def push_enabled():
    cfg = current_app.config
    return bool(cfg.get("VAPID_PUBLIC_KEY") and cfg.get("VAPID_PRIVATE_KEY") and cfg.get("VAPID_SUBJECT"))


def queue(user_id, title, body, link):
    """Called by notify(); sent only if the surrounding transaction commits."""
    if not has_app_context() or not push_enabled():
        return
    db.session.info.setdefault(PENDING_KEY, []).append((user_id, title, body or "", link or "/app/"))


def _deliver(items):
    from pywebpush import WebPushException, webpush
    cfg = current_app.config
    user_ids = {u for u, *_ in items}
    subs = PushSubscription.query.filter(PushSubscription.user_id.in_(user_ids)).all()
    by_user = {}
    for s in subs:
        by_user.setdefault(s.user_id, []).append(s)
    dead, ok = [], []
    for user_id, title, body, link in items:
        payload = json.dumps({"title": title[:120], "body": body[:240], "url": _app_url(link)})
        for sub in by_user.get(user_id, []):
            try:
                webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, data=payload,
                        vapid_private_key=cfg["VAPID_PRIVATE_KEY"], vapid_claims={"sub": cfg["VAPID_SUBJECT"]},
                        timeout=5, ttl=86400)
                ok.append(sub.id)
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                if status in (404, 410):
                    dead.append(sub.id)
                else:
                    current_app.logger.warning("Push failed (%s) for subscription %s", status, sub.id)
            except Exception as exc:  # network errors must never break the request
                current_app.logger.warning("Push failed for subscription %s: %s", sub.id, exc)
    if dead:
        PushSubscription.query.filter(PushSubscription.id.in_(dead)).delete(synchronize_session=False)
    if ok:
        PushSubscription.query.filter(PushSubscription.id.in_(ok)).update({"last_success_at": utcnow()}, synchronize_session=False)
    if dead or ok:
        db.session.commit()


def _app_url(link):
    if link == "/me":
        return "/app/activity?tab=notifications"
    if link.startswith("/dashboard"):
        return "/app/" + (("?" + link.split("?", 1)[1]) if "?" in link else "")
    return link if link.startswith("/app/") else "/app/"


_registered = False


def register(app):
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(Session, "after_commit")
    def _send_after_commit(session):
        items = session.info.pop(PENDING_KEY, None)
        if items and has_request_context():
            # Delivered once the response is ready; _deliver commits its own small update.
            g.setdefault("push_outbox", []).extend(items)

    @event.listens_for(Session, "after_rollback")
    def _drop_on_rollback(session):
        session.info.pop(PENDING_KEY, None)

    @app.after_request
    def _flush_push(response):
        items = g.pop("push_outbox", None)
        if items:
            try:
                _deliver(items)
            except Exception as exc:
                app.logger.warning("Push delivery skipped: %s", exc)
        return response
