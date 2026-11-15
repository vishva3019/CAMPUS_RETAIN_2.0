"""Phase 3: the JSON API used by the React frontend, and serving the built app."""
import csv
import io
import os

import pytest

from campus_retain.extensions import db
from campus_retain.models import AuditLog, Claim, ClaimStatus, CollectionPoint, College, Notification, User
from campus_retain.services.audit import notify

from .conftest import api_token, last_code, login, make_college, make_item, make_user


@pytest.fixture
def world(new_client):
    college = make_college(contact_email="lf@alpha.edu.in")
    other = make_college(slug="beta", domains=("beta.edu.in",))
    for email, c, role in [("s1@alpha.edu.in", college, "student"), ("s2@alpha.edu.in", college, "student"),
                           ("admin@alpha.edu.in", college, "college_admin"),
                           ("guard@alpha.edu.in", college, "security_staff"),
                           ("admin@beta.edu.in", other, "college_admin"),
                           ("root@platform.test", None, "platform_super_admin")]:
        make_user(email, c, role=role)
    clients = {}
    for email in ("s1@alpha.edu.in", "s2@alpha.edu.in", "admin@alpha.edu.in", "guard@alpha.edu.in",
                  "admin@beta.edu.in", "root@platform.test"):
        cl = new_client()
        login(cl, email, path="/admin_login" if "admin" in email or "root" in email else "/login")
        clients[email.split("@")[0] + ("@beta" if "beta" in email else "")] = (cl, api_token(cl))
    return college, other, clients


def get(ct, path):
    return ct[0].get(path)


def post(ct, path, **body):
    resp = ct[0].post(path, headers={"X-CSRFToken": ct[1]}, json=body)
    db.session.expire_all()
    return resp


def test_session_requires_login_and_reports_permissions(world, client):
    assert client.get("/api/v1/session").status_code == 401
    _, _, c = world
    s = get(c["s1"], "/api/v1/session").get_json()
    assert s["user"]["email"] == "s1@alpha.edu.in" and "claims.submit" in s["user"]["permissions"]
    assert "claims.review" not in s["user"]["permissions"]
    assert s["college"]["slug"] == "alpha" and s["csrf_token"] and s["config"]["max_photos"] == 3
    root = get(c["root"], "/api/v1/session").get_json()
    assert root["college"] is None and "platform.manage" in root["user"]["permissions"]


def test_csrf_required_on_api_writes(world):
    _, _, c = world
    resp = c["s1"][0].post("/api/v1/notifications/read", json={})
    assert resp.status_code == 400


def test_items_are_scoped_and_hide_private_fields(world):
    college, other, c = world
    mine = make_item(college, name="Alpha wallet", secret_detail="SECRET-123")
    make_item(other, name="Beta wallet")
    data = get(c["s2"], "/api/v1/items").get_json()
    assert [i["name"] for i in data["items"]] == ["Alpha wallet"]
    item = data["items"][0]
    assert "secret_detail" not in item and "claims" not in item and item["can_claim"] is True
    assert "SECRET-123" not in get(c["s2"], "/api/v1/items").get_data(as_text=True)
    assert get(c["s2"], "/api/v1/items?q=alpha").get_json()["total"] == 1
    assert get(c["s2"], "/api/v1/items?q=zzz").get_json()["total"] == 0
    assert get(c["s2"], "/api/v1/items?kind=lost").get_json()["total"] == 0
    assert get(c["s2"], "/api/v1/items?kind=bogus").status_code == 400
    assert mine.id


def test_admin_items_show_claims_and_secrets_to_reviewers_only(world, outbox):
    college, _, c = world
    item = make_item(college, secret_detail="SECRET-123")
    post(c["s1"], "/api/claim", item_id=item.id, student_id="21CS1", proof_description="sticker")
    data = get(c["admin"], "/api/v1/admin/items?status=pending").get_json()
    row = data["items"][0]
    assert row["secret_detail"] == "SECRET-123" and row["claims"][0]["student_email"] == "s1@alpha.edu.in"
    assert data["counts"]["Pending"] == 1
    guard = get(c["guard"], "/api/v1/admin/items").get_json()["items"][0]
    assert "secret_detail" not in guard and "student_email" not in guard["claims"][0]
    assert get(c["s1"], "/api/v1/admin/items").status_code == 403
    assert get(c["admin@beta"], "/api/v1/admin/items").get_json()["total"] == 0


def test_csv_export_is_scoped_escaped_and_audited(world):
    college, other, c = world
    make_item(college, name="=HYPERLINK(\"http://x\")", secret_detail="SECRET-123")
    make_item(other, name="Beta only")
    resp = get(c["admin"], "/api/v1/admin/items.csv")
    assert resp.status_code == 200 and resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True).lstrip("﻿"))))
    assert rows[0][0] == "Item ID" and len(rows) == 2
    assert rows[1][2].startswith("'=")                           # formula neutralised
    body = resp.get_data(as_text=True)
    assert "SECRET-123" not in body and "Beta only" not in body
    assert AuditLog.query.filter_by(action="items.exported").count() == 1
    assert get(c["s1"], "/api/v1/admin/items.csv").status_code == 403
    assert get(c["guard"], "/api/v1/admin/items.csv").status_code == 403


def test_activity_and_notifications(world, outbox):
    college, _, c = world
    item = make_item(college)
    post(c["s2"], "/api/claim", item_id=item.id, student_id="1", proof_description="dent")
    act = get(c["s2"], "/api/v1/me/activity").get_json()
    assert act["claims"][0]["status"] == "pending" and act["claims"][0]["pickup"] is None

    s2 = User.query.filter_by(email="s2@alpha.edu.in").one()
    s1 = User.query.filter_by(email="s1@alpha.edu.in").one()
    notify(s1, "x", "Not yours")
    db.session.commit()
    notes = get(c["s2"], "/api/v1/notifications").get_json()
    assert notes["unread"] == 1 and [n["title"] for n in notes["items"]] == ["Claim submitted for Black wallet"]
    other_id = Notification.query.filter_by(user_id=s1.id).one().id
    assert post(c["s2"], "/api/v1/notifications/read", ids=[other_id]).get_json()["marked"] == 0
    assert post(c["s2"], "/api/v1/notifications/read", ids="all").status_code == 400
    done = post(c["s2"], "/api/v1/notifications/read").get_json()
    assert done["marked"] == 1 and done["unread"] == 0
    assert Notification.query.filter_by(user_id=s2.id, read_at=None).count() == 0
    assert Notification.query.filter_by(user_id=s1.id, read_at=None).count() == 1

    post(c["admin"], f"/api/admin/approve/{item.id}")
    claim = get(c["s2"], "/api/v1/me/activity").get_json()["claims"][0]
    assert claim["status"] == "approved" and claim["pickup"]["code_sent_at"]
    assert post(c["s2"], f"/api/v1/me/claims/{claim['id']}/pickup-code").status_code == 429   # just sent
    assert post(c["s1"], f"/api/v1/me/claims/{claim['id']}/pickup-code").status_code == 404   # not theirs


def test_withdraw_and_close_lost_via_api(world):
    college, _, c = world
    item = make_item(college)
    post(c["s2"], "/api/claim", item_id=item.id, student_id="1", proof_description="x")
    claim_id = Claim.query.one().id
    assert post(c["s1"], f"/api/v1/me/claims/{claim_id}/withdraw").status_code == 404
    assert post(c["s2"], f"/api/v1/me/claims/{claim_id}/withdraw").status_code == 200
    assert db.session.get(Claim, claim_id).status == ClaimStatus.WITHDRAWN
    lost = make_item(college, name="Umbrella", kind="lost", reporter=User.query.filter_by(email="s1@alpha.edu.in").one())
    assert post(c["s2"], f"/api/v1/me/lost/{lost.id}/found").status_code == 404
    assert post(c["s1"], f"/api/v1/me/lost/{lost.id}/explode").status_code == 400
    assert post(c["s1"], f"/api/v1/me/lost/{lost.id}/found").status_code == 200


def test_desk_api_hands_over_with_code(world, outbox):
    college, _, c = world
    item = make_item(college)
    post(c["s2"], "/api/claim", item_id=item.id, student_id="1", proof_description="x")
    post(c["admin"], f"/api/admin/approve/{item.id}")
    code = last_code(outbox, "s2@alpha.edu.in")
    desk = get(c["guard"], "/api/v1/desk").get_json()
    claim_id = desk["items"][0]["id"]
    assert desk["items"][0]["has_code"] is True
    bad = post(c["guard"], f"/api/v1/desk/{claim_id}/verify", code="000000" if code != "000000" else "111111")
    assert bad.status_code == 400 and "tries left" in bad.get_json()["error"]
    assert post(c["admin@beta"], f"/api/v1/desk/{claim_id}/verify", code=code).status_code == 404
    assert post(c["s1"], f"/api/v1/desk/{claim_id}/verify", code=code).status_code == 403
    ok = post(c["guard"], f"/api/v1/desk/{claim_id}/verify", code=code)
    assert ok.status_code == 200 and ok.get_json()["claim"]["collected_by"] == "guard@alpha.edu.in"
    assert get(c["guard"], "/api/v1/desk").get_json()["recent"][0]["id"] == claim_id


def test_collection_points_api(world):
    college, _, c = world
    assert post(c["admin"], "/api/v1/admin/collection-points", name="").status_code == 400
    resp = post(c["admin"], "/api/v1/admin/collection-points", name="Gate cabin", opening_hours="9-5")
    point = resp.get_json()["point"]
    assert point["name"] == "Gate cabin" and point["is_active"]
    assert post(c["admin"], "/api/v1/admin/collection-points", name="gate CABIN").status_code == 400
    assert post(c["guard"], "/api/v1/admin/collection-points", name="X").status_code == 403
    assert [p["name"] for p in get(c["s1"], "/api/v1/collection-points").get_json()["items"]] == ["Gate cabin"]
    assert post(c["admin@beta"], f"/api/v1/admin/collection-points/{point['id']}/toggle").status_code == 404
    assert post(c["admin"], f"/api/v1/admin/collection-points/{point['id']}/toggle").get_json()["point"]["is_active"] is False
    assert get(c["s1"], "/api/v1/collection-points").get_json()["items"] == []
    assert CollectionPoint.query.count() == 1


def test_platform_api(world, outbox):
    _, _, c = world
    data = get(c["root"], "/api/v1/platform/colleges").get_json()
    assert data["totals"]["colleges"] == 2 and "secret" not in str(data)
    assert get(c["admin"], "/api/v1/platform/colleges").status_code == 403
    assert post(c["root"], "/api/v1/platform/colleges", name="Gamma", slug="Bad Slug!", domains="gamma.edu").status_code == 400
    assert post(c["root"], "/api/v1/platform/colleges", name="Gamma", slug="gamma", domains="alpha.edu.in").status_code == 400
    new = post(c["root"], "/api/v1/platform/colleges", name="Gamma", slug="gamma", domains="gamma.edu.in")
    gid = new.get_json()["id"]
    assert db.session.get(College, gid).status == "pending"
    assert post(c["root"], f"/api/v1/platform/colleges/{gid}/status", status="bogus").status_code == 400
    assert post(c["root"], f"/api/v1/platform/colleges/{gid}/status", status="active").status_code == 200
    assert post(c["root"], f"/api/v1/platform/colleges/{gid}/admins", email="head@gamma.edu.in").status_code == 200
    assert post(c["root"], f"/api/v1/platform/colleges/{gid}/admins", email="head@gamma.edu.in").status_code == 400
    assert any(m["to"] == "head@gamma.edu.in" for m in outbox)


@pytest.fixture
def built_app(app, tmp_path):
    """Pretend a frontend build exists and the React app is switched on."""
    old_static = app.static_folder
    (tmp_path / "app" / "assets").mkdir(parents=True)
    (tmp_path / "app" / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "app" / "assets" / "main.js").write_text("console.log(1)")
    app.static_folder = str(tmp_path)
    app.config["USE_REACT_APP"] = True
    yield app
    app.static_folder = old_static
    app.config["USE_REACT_APP"] = False


def test_spa_shell_routes_and_login_redirect(built_app, new_client):
    college = make_college()
    make_user("s1@alpha.edu.in", college)
    make_user("admin@alpha.edu.in", college, role="college_admin")
    anon = new_client()
    assert anon.get("/app/activity").status_code == 302                 # sign in first
    assert anon.get("/login").location.endswith("/app/signin")          # React sign-in is the default
    for public in ("/app/welcome", "/app/join", "/app/signin", "/"):
        assert anon.get(public).status_code == 200                      # onboarding needs no account
    student = new_client()
    assert login(student, "s1@alpha.edu.in", path="/admin_login").location.endswith("/app/")
    assert student.get("/app/signin").status_code == 302                # returning users skip sign-in
    page = student.get("/app/activity")
    assert page.status_code == 200 and b'id=root' in page.data and page.headers["Cache-Control"] == "no-store"
    asset = student.get("/app/assets/main.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["Cache-Control"]
    assert student.get("/app/assets/missing.js").status_code == 404
    assert student.get("/app/assets/../index.html").status_code in (200, 404)  # never escapes the build dir
    admin = new_client()
    assert login(admin, "admin@alpha.edu.in", path="/admin_login").location.endswith("/app/admin")
    assert student.get("/dashboard").status_code == 200                  # classic pages still work


def test_spa_404_without_build(app, new_client):
    college = make_college()
    make_user("s1@alpha.edu.in", college)
    cl = new_client()
    assert login(cl, "s1@alpha.edu.in").location.endswith("/dashboard")   # React app off in tests
    old = app.static_folder
    app.static_folder = os.path.join(old, "does-not-exist")
    try:
        assert cl.get("/app/").status_code == 404
    finally:
        app.static_folder = old
