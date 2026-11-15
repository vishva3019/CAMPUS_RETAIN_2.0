"""UX polish: filters, item details, report flow, claim tracking, pickup codes in the app,
notification links, the admin review queue and pickup reminders."""
import re
from datetime import date, timedelta

import pytest

from campus_retain.extensions import db
from campus_retain.models import Campus, Claim, ClaimStatus, Item, ItemKind, ItemStatus, Notification, utcnow

from .conftest import api_token, login, make_college, make_item, make_user


@pytest.fixture
def world(new_client):
    college = make_college()
    other = make_college(slug="beta", domains=("beta.edu.in",))
    users = {}
    for email, c, role in [("s1@alpha.edu.in", college, "student"), ("s2@alpha.edu.in", college, "student"),
                           ("admin@alpha.edu.in", college, "college_admin"),
                           ("admin@beta.edu.in", other, "college_admin")]:
        users[email] = make_user(email, c, role=role)
    clients = {}
    for email in users:
        cl = new_client()
        login(cl, email, path="/admin_login")
        clients[email.split("@")[0] + ("@beta" if "beta" in email else "")] = (cl, api_token(cl))
    return college, other, users, clients


def get(ct, path):
    db.session.expire_all()
    return ct[0].get(path)


def post(ct, path, json=None, data=None):
    resp = ct[0].post(path, headers={"X-CSRFToken": ct[1]}, json=json if data is None else None, data=data)
    db.session.expire_all()
    return resp


def claim(ct, item, proof="It has my name sticker inside"):
    return post(ct, "/api/claim", json={"item_id": item.id, "student_id": "1AB22CS001", "proof_description": proof})


# ---------------------------------------------------------------- browsing

def test_filters_status_date_place_campus(world):
    college, _o, users, c = world
    main = Campus(college_id=college.id, name="Main")
    north = Campus(college_id=college.id, name="North")
    db.session.add_all([main, north])
    db.session.commit()
    make_item(college, "Blue bottle", location="Library 2nd floor", campus=main)
    make_item(college, "Red umbrella", location="Canteen", campus=north, status=ItemStatus.RETURNED)
    old = make_item(college, "Old calculator", location="Exam hall")
    old.date_found = utcnow() - timedelta(days=40)
    db.session.commit()

    names = lambda q: sorted(i["name"] for i in get(c["s1"], "/api/v1/items" + q).get_json()["items"])
    assert names("") == ["Blue bottle", "Old calculator", "Red umbrella"]            # default: everything visible
    assert names("?availability=open") == ["Blue bottle", "Old calculator"]           # returned hidden
    assert names("?availability=returned") == ["Red umbrella"]
    assert names("?since=30") == ["Blue bottle", "Red umbrella"]
    assert names("?place=library") == ["Blue bottle"]
    assert names(f"?campus={north.id}") == ["Red umbrella"]
    assert names("?q=library") == ["Blue bottle"]                                   # search includes the place


def test_item_details_never_leak_private_fields(world):
    college, other, users, c = world
    item = make_item(college, "Black wallet", reporter=users["s2@alpha.edu.in"], secret_detail="PHOTO-OF-CAT")
    resp = get(c["s1"], f"/api/v1/items/{item.id}")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and resp.get_json()["ref"] == f"F-{item.id:05d}"
    assert "PHOTO-OF-CAT" not in body and "s2@alpha.edu.in" not in body
    assert resp.get_json()["can_claim"] is True and resp.get_json()["my_claim"] is None
    assert get(c["admin@beta"], f"/api/v1/items/{item.id}").status_code == 404     # other college

    claim(c["s1"], item)
    data = get(c["s1"], f"/api/v1/items/{item.id}").get_json()
    assert data["my_claim"]["status"] == "pending" and data["can_claim"] is False


def test_closed_lost_report_hidden_except_from_owner(world):
    college, _o, users, c = world
    lost = make_item(college, "Keys", kind=ItemKind.LOST, reporter=users["s2@alpha.edu.in"], status=ItemStatus.RETURNED)
    assert get(c["s1"], f"/api/v1/items/{lost.id}").status_code == 404
    assert get(c["s2"], f"/api/v1/items/{lost.id}").status_code == 200


# ---------------------------------------------------------------- reporting and matching

def test_report_returns_reference_and_suggests_found_items(world):
    college, _o, users, c = world
    found = make_item(college, "Black leather wallet", category="Accessories", location="Library",
                      occurred_on=date.today(), reporter=users["s2@alpha.edu.in"])
    resp = post(c["s1"], "/api/report", data={"kind": "lost", "name": "Black leather wallet", "category": "Accessories",
                                              "location": "Library", "occurred_on": (date.today() - timedelta(days=1)).isoformat()})
    body = resp.get_json()
    assert resp.status_code == 200 and re.fullmatch(r"L-\d{5}", body["ref"])
    assert [s["id"] for s in body["suggestions"]] == [found.id]
    assert "secret_detail" not in body["suggestions"][0]


def test_found_before_lost_is_not_a_match(world):
    college, _o, users, c = world
    lost = make_item(college, "Grey hoodie", kind=ItemKind.LOST, category="Clothing", location="Gym",
                     occurred_on=date.today(), reporter=users["s1@alpha.edu.in"])
    # Found 10 days *before* it was lost: can't be the same hoodie.
    resp = post(c["s2"], "/api/report", data={"kind": "found", "name": "Grey hoodie", "category": "Clothing", "location": "Gym",
                                              "occurred_on": (date.today() - timedelta(days=10)).isoformat()})
    assert resp.get_json()["owners_alerted"] == 0
    resp = post(c["s2"], "/api/report", data={"kind": "found", "name": "Grey hoodie", "category": "Clothing", "location": "Gym",
                                              "occurred_on": date.today().isoformat()})
    assert resp.get_json()["owners_alerted"] == 1
    note = Notification.query.filter_by(user_id=lost.reported_by_id, kind="lost.suggested_match").one()
    item_id = resp.get_json()["id"]
    data = get(c["s1"], "/api/v1/notifications").get_json()["items"][0]
    assert note.link == f"/app/?item={item_id}" and data["link"] == f"/app/?item={item_id}"


# ---------------------------------------------------------------- claims, codes, notifications

def test_claim_stages_and_pickup_code_shown_in_app(world, app):
    college, _o, users, c = world
    item = make_item(college, "Black wallet")
    claim(c["s1"], item)
    claim_row = Claim.query.one()
    acts = get(c["s1"], "/api/v1/me/activity").get_json()["claims"]
    assert acts[0]["stage"] == "under_review" and acts[0]["item"]["ref"] == f"F-{item.id:05d}"

    post(c["admin"], f"/api/admin/approve/{item.id}", json={"remarks": "Matches the sticker"})
    acts = get(c["s1"], "/api/v1/me/activity").get_json()["claims"]
    assert acts[0]["stage"] == "awaiting_pickup" and acts[0]["pickup"]["instructions"]

    # The claimant can see a fresh code in the app (60 s after the approval email).
    assert post(c["s1"], f"/api/v1/me/claims/{claim_row.id}/pickup-code").status_code == 429
    claim_row = db.session.get(Claim, claim_row.id)
    claim_row.pickup_code_sent_at = utcnow() - timedelta(minutes=5)
    db.session.commit()
    resp = post(c["s1"], f"/api/v1/me/claims/{claim_row.id}/pickup-code")
    code = resp.get_json()["code"]
    assert resp.status_code == 200 and re.fullmatch(r"\d{6}", code) and resp.headers["Cache-Control"] == "no-store"
    assert post(c["s2"], f"/api/v1/me/claims/{claim_row.id}/pickup-code").status_code == 404     # not theirs
    assert code not in (db.session.get(Claim, claim_row.id).pickup_code_hash or "")

    assert post(c["admin"], f"/api/v1/desk/{claim_row.id}/verify", json={"code": code}).status_code == 200
    acts = get(c["s1"], "/api/v1/me/activity").get_json()["claims"]
    assert acts[0]["stage"] == "returned" and acts[0]["collected_at"]
    assert db.session.get(Item, item.id).status == ItemStatus.RETURNED
    assert [i["id"] for i in get(c["s1"], "/api/v1/items?availability=open").get_json()["items"]] == []

    kinds = [n["kind"] for n in get(c["s1"], "/api/v1/notifications").get_json()["items"]]
    assert {"claim.submitted", "claim.approved", "claim.collected"} <= set(kinds)
    links = {n["kind"]: n["link"] for n in get(c["s1"], "/api/v1/notifications").get_json()["items"]}
    assert links["claim.approved"] == f"/app/activity?claim={claim_row.id}"


def test_legacy_notification_links_point_at_the_app(world):
    college, _o, users, c = world
    from campus_retain.services.audit import notify
    notify(users["s1@alpha.edu.in"], "x", "Old one", link="/me")
    notify(users["s1@alpha.edu.in"], "y", "Old two", link="/dashboard?q=wallet")
    db.session.commit()
    links = sorted(n["link"] for n in get(c["s1"], "/api/v1/notifications").get_json()["items"])
    assert links == ["/app/?q=wallet", "/app/activity"]


def test_mark_single_notification_read(world):
    college, _o, users, c = world
    from campus_retain.services.audit import notify
    a = notify(users["s1@alpha.edu.in"], "x", "One")
    notify(users["s1@alpha.edu.in"], "x", "Two")
    db.session.commit()
    resp = post(c["s1"], "/api/v1/notifications/read", json={"ids": [a.id]})
    assert resp.get_json()["unread"] == 1


# ---------------------------------------------------------------- admin queue

def test_admin_review_queue(world):
    college, other, users, c = world
    item = make_item(college, "Black wallet", secret_detail="CAT-LOCKSCREEN")
    claim(c["s1"], item, proof="Lock screen is my cat")
    resp = get(c["admin"], "/api/v1/admin/claims")
    data = resp.get_json()
    assert resp.status_code == 200 and data["total"] == 1
    row = data["items"][0]
    assert row["proof_description"] == "Lock screen is my cat"
    assert row["item"]["secret_detail"] == "CAT-LOCKSCREEN" and row["student_email"] == "s1@alpha.edu.in"
    assert get(c["s1"], "/api/v1/admin/claims").status_code == 403
    assert get(c["admin@beta"], "/api/v1/admin/claims").get_json()["total"] == 0
    post(c["admin"], f"/api/admin/reject/{item.id}", json={"remarks": "Proof didn't match"})
    assert get(c["admin"], "/api/v1/admin/claims").get_json()["total"] == 0
    assert get(c["s1"], "/api/v1/me/activity").get_json()["claims"][0]["stage"] == "rejected"


# ---------------------------------------------------------------- reminders

def test_pickup_reminders_once_and_cron_auth(world, app, client, outbox):
    college, _o, users, c = world
    item = make_item(college, "Black wallet")
    claim(c["s1"], item)
    post(c["admin"], f"/api/admin/approve/{item.id}", json={})
    row = Claim.query.one()
    row.reviewed_at = utcnow() - timedelta(days=app.config["PICKUP_REMINDER_DAYS"] + 1)
    db.session.commit()

    assert client.get("/internal/cron/pickup-reminders").status_code == 404          # no secret set
    app.config["CRON_SECRET"] = "s3cret-value"
    try:
        assert client.get("/internal/cron/pickup-reminders", headers={"Authorization": "Bearer nope"}).status_code == 404
        resp = client.get("/internal/cron/pickup-reminders", headers={"Authorization": "Bearer s3cret-value"})
        assert resp.status_code == 200 and resp.get_json()["reminders_sent"] == 1
        resp = client.get("/internal/cron/pickup-reminders", headers={"Authorization": "Bearer s3cret-value"})
        assert resp.get_json()["reminders_sent"] == 0                                 # only once
    finally:
        app.config["CRON_SECRET"] = None
    assert Notification.query.filter_by(kind="pickup.reminder").count() == 1
    assert any("Reminder" in m["subject"] for m in outbox)


def test_welcome_greeting_shows_once_after_sign_in(world, new_client):
    cl = new_client()
    login(cl, "s1@alpha.edu.in", path="/admin_login")
    assert cl.get("/api/v1/session").get_json()["greet"] is True
    assert cl.get("/api/v1/session").get_json()["greet"] is False      # only the first load
    cl.get("/logout")
    login(cl, "s1@alpha.edu.in", path="/admin_login")                  # signing in again greets again
    assert cl.get("/api/v1/session").get_json()["greet"] is True
