"""Phase 7: plans assigned by hand, feature gates, Redis config, Sentry scrubbing, Web Push."""
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from campus_retain.config import load_config
from campus_retain.extensions import db
from campus_retain.models import PushSubscription, Subscription, User, utcnow
from campus_retain.services import monitoring

from .conftest import api_token, login, make_college, make_item, make_user


@pytest.fixture
def world(new_client):
    a = make_college()
    b = make_college(slug="beta", domains=("beta.edu.in",))
    make_user("s1@alpha.edu.in", a)
    make_user("admin@alpha.edu.in", a, role="college_admin")
    make_user("admin@beta.edu.in", b, role="college_admin")
    make_user("s2@beta.edu.in", b)
    make_user("root@platform.test", None, role="platform_super_admin")
    cl = {}
    for email in ("s1@alpha.edu.in", "admin@alpha.edu.in", "admin@beta.edu.in", "s2@beta.edu.in", "root@platform.test"):
        c = new_client()
        login(c, email, path="/login" if email.startswith("s") else "/admin_login")
        cl[email.split("@")[0] + ("@beta" if "beta" in email else "")] = (c, api_token(c))
    return a, b, cl


def post(ct, path, **body):
    r = ct[0].post(path, headers={"X-CSRFToken": ct[1]}, json=body)
    db.session.expire_all()
    return r


def assign(cl, college, plan, **kw):
    return post(cl["root"], f"/api/v1/platform/colleges/{college.id}/plan", plan=plan, **kw)


def test_unassigned_colleges_are_on_pilot_with_everything(world):
    a, _, cl = world
    plan = cl["admin"][0].get("/api/v1/session").get_json()["college"]["plan"]
    assert plan["key"] == "pilot" and "analytics" in plan["features"]
    assert cl["admin"][0].get("/api/v1/admin/analytics").status_code == 200


def test_free_plan_gates_features_and_limits_collection_points(world):
    a, _, cl = world
    assert assign(cl, a, "free", reference="INV-001").status_code == 200
    r = cl["admin"][0].get("/api/v1/admin/analytics")
    assert r.status_code == 403 and r.get_json()["plan_required"] == "analytics"
    assert cl["admin"][0].get("/api/v1/admin/items.csv").status_code == 403
    assert post(cl["admin"], "/api/v1/admin/events", name="Fest", starts_on="2026-11-14", ends_on="2026-11-15").status_code == 403
    assert post(cl["admin"], "/api/v1/admin/settings", inter_college_matching=True).status_code == 403
    for n in ("A", "B"):
        assert post(cl["admin"], "/api/v1/admin/collection-points", name=f"Desk {n}").status_code == 200
    third = post(cl["admin"], "/api/v1/admin/collection-points", name="Desk C")
    assert third.status_code == 400 and "plan allows 2" in third.get_json()["error"]
    # core lost & found still works
    assert cl["s1"][0].get("/api/v1/items").status_code == 200
    assign(cl, a, "standard")
    assert cl["admin"][0].get("/api/v1/admin/analytics").status_code == 200
    assert post(cl["admin"], "/api/v1/admin/collection-points", name="Desk C").status_code == 200


def test_expired_or_cancelled_plan_falls_back_to_free(world):
    a, _, cl = world
    assign(cl, a, "premium", period_end=(utcnow() + timedelta(days=30)).date().isoformat())
    assert cl["admin"][0].get("/api/v1/admin/analytics").status_code == 200
    sub = Subscription.query.filter_by(college_id=a.id).one()
    sub.current_period_end = utcnow() - timedelta(days=1)
    db.session.commit()
    plan = cl["admin"][0].get("/api/v1/session").get_json()["college"]["plan"]
    assert plan["key"] == "free" and "ended" in plan["note"]
    assert cl["admin"][0].get("/api/v1/admin/analytics").status_code == 403
    assign(cl, a, "premium", status="cancelled")
    assert cl["admin"][0].get("/api/v1/session").get_json()["college"]["plan"]["key"] == "free"


def test_plan_assignment_is_platform_only_validated_and_audited(world):
    a, _, cl = world
    assert post(cl["admin"], f"/api/v1/platform/colleges/{a.id}/plan", plan="premium").status_code == 403
    assert assign(cl, a, "gold").status_code == 400
    assert assign(cl, a, "standard", period_end="2001-01-01").status_code == 400
    assign(cl, a, "standard", reference="UTR 12345")
    assign(cl, a, "premium", reference="UTR 67890")
    assert Subscription.query.filter_by(college_id=a.id).count() == 2           # history kept
    rows = cl["root"][0].get("/api/v1/platform/plans").get_json()
    me = next(c for c in rows["colleges"] if c["id"] == a.id)
    assert me["plan"]["key"] == "premium" and me["reference"] == "UTR 67890"
    from campus_retain.models import AuditLog
    assert AuditLog.query.filter_by(action="plan.assigned").count() == 2


def test_network_excludes_colleges_whose_plan_lacks_it(world):
    a, b, cl = world
    post(cl["admin"], "/api/v1/admin/settings", inter_college_matching=True)
    post(cl["admin@beta"], "/api/v1/admin/settings", inter_college_matching=True)
    make_item(a, name="Alpha laptop")
    assert cl["s2@beta"][0].get("/api/v1/network/items").get_json()["total"] == 1
    assign(cl, a, "free")
    assert cl["s2@beta"][0].get("/api/v1/network/items").get_json()["total"] == 0


def test_ai_needs_premium(world, app):
    a, _, cl = world
    app.config["ANTHROPIC_API_KEY"] = "test-key-not-real"
    try:
        assign(cl, a, "standard")
        assert cl["s1"][0].get("/api/v1/session").get_json()["config"]["ai_enabled"] is False
        assign(cl, a, "premium")
        assert cl["s1"][0].get("/api/v1/session").get_json()["config"]["ai_enabled"] is True
    finally:
        app.config["ANTHROPIC_API_KEY"] = None


def test_redis_url_feeds_rate_limit_storage(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "rediss://default:x@example.upstash.io:6379")
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql:///x")
    assert load_config("production")["RATELIMIT_STORAGE_URI"].startswith("rediss://")
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "redis://explicit:6379")
    assert load_config("production")["RATELIMIT_STORAGE_URI"] == "redis://explicit:6379"


def test_sentry_is_off_without_dsn_and_scrubs_personal_data(app, monkeypatch):
    assert monitoring.init_sentry(app) is False
    event = {"request": {"cookies": {"session": "abc"}, "data": {"password": "x"}, "query_string": "email=a@b",
                         "headers": {"Cookie": "session=abc", "X-CSRFToken": "t", "User-Agent": "UA"}},
             "user": {"id": 7, "email": "s1@alpha.edu.in", "ip_address": "1.2.3.4"}}
    out = monitoring.before_send(event, None)
    assert "cookies" not in out["request"] and "data" not in out["request"] and "query_string" not in out["request"]
    assert out["request"]["headers"]["Cookie"] == "[removed]" and out["request"]["headers"]["User-Agent"] == "UA"
    assert out["user"] == {"id": 7}
    calls = []
    import sentry_sdk
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    app.config["SENTRY_DSN"] = "https://public@o0.ingest.sentry.io/0"
    try:
        from flask import Flask
        dummy = Flask("x")
        dummy.config.update(app.config)
        assert monitoring.init_sentry(dummy) is True
        assert calls[0]["send_default_pii"] is False and calls[0]["before_send"] is monitoring.before_send
    finally:
        app.config["SENTRY_DSN"] = None


# ---------------------------------------------------------------- Web Push

@pytest.fixture
def push_on(app, monkeypatch):
    app.config.update(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", VAPID_SUBJECT="mailto:ops@example.com")
    sent = []

    class FakeExc(Exception):
        def __init__(self, status):
            super().__init__("push failed")
            self.response = SimpleNamespace(status_code=status)

    behaviour = {"status": None}

    def fake_webpush(sub, data=None, **kw):
        if behaviour["status"]:
            raise FakeExc(behaviour["status"])
        sent.append((sub["endpoint"], json.loads(data), kw))

    import pywebpush
    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    monkeypatch.setattr(pywebpush, "WebPushException", FakeExc)
    yield sent, behaviour
    app.config.update(VAPID_PUBLIC_KEY=None, VAPID_PRIVATE_KEY=None, VAPID_SUBJECT=None)


def subscribe(ct, endpoint="https://push.example.com/abc"):
    return post(ct, "/api/v1/push/subscribe", endpoint=endpoint, keys={"p256dh": "k" * 20, "auth": "a" * 10})


def test_push_disabled_without_keys(world):
    _, _, cl = world
    assert cl["s1"][0].get("/api/v1/push/key").get_json() == {"enabled": False, "public_key": None}
    assert subscribe(cl["s1"]).status_code == 503


def test_notifications_are_pushed_after_commit(world, push_on):
    a, _, cl = world
    sent, behaviour = push_on
    assert cl["s1"][0].get("/api/v1/push/key").get_json()["public_key"] == "pub"
    assert post(cl["s1"], "/api/v1/push/subscribe", endpoint="http://insecure", keys={"p256dh": "k", "auth": "a"}).status_code == 400
    assert subscribe(cl["s1"]).status_code == 200
    item = make_item(a)
    post(cl["s1"], "/api/claim", item_id=item.id, student_id="1", proof_description="sticker inside")
    assert len(sent) == 1
    endpoint, payload, kw = sent[0]
    assert endpoint == "https://push.example.com/abc" and payload["title"].startswith("Claim submitted")
    assert payload["url"].startswith("/app/") and kw["vapid_claims"] == {"sub": "mailto:ops@example.com"}
    # a rejected claim (no commit of a notification) sends nothing
    sent.clear()
    post(cl["s1"], "/api/claim", item_id=item.id, student_id="1", proof_description="again")
    assert sent == []
    # dead subscription is removed
    behaviour["status"] = 410
    post(cl["admin"], f"/api/admin/approve/{item.id}")
    assert PushSubscription.query.count() == 0


def test_shared_browser_moves_to_the_latest_user(world, push_on):
    _, _, cl = world
    subscribe(cl["s1"], "https://push.example.com/shared")
    subscribe(cl["admin"], "https://push.example.com/shared")
    sub = PushSubscription.query.one()
    assert sub.user_id == User.query.filter_by(email="admin@alpha.edu.in").one().id
    post(cl["s1"], "/api/v1/push/unsubscribe", endpoint="https://push.example.com/shared")
    assert PushSubscription.query.count() == 1                          # not theirs any more
    post(cl["admin"], "/api/v1/push/unsubscribe", endpoint="https://push.example.com/shared")
    assert PushSubscription.query.count() == 0


def test_vapid_key_command(app):
    out = app.test_cli_runner().invoke(args=["push", "vapid-keys"]).output
    lines = dict(l.split("=", 1) for l in out.strip().splitlines())
    assert len(lines["VAPID_PUBLIC_KEY"]) == 87 and len(lines["VAPID_PRIVATE_KEY"]) == 43
